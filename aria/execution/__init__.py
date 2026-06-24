"""Execution layer — the ONLY module allowed to sign/send transactions.

Mechanism: MCP client to a long-lived `twak serve` subprocess (twak_client.py).
Every swap is gated: quote first -> price-impact check -> execute -> log.
Failure policy (docs/DESIGN.md): a failed swap is retried at most ONCE (transport
errors only); reverts are never auto-retried — recompute next cycle.

Real execution requires EXECUTION_MODE=live + NETWORK=mainnet + not dry_run.
Everything else returns 'skipped' so the rest of the pipeline still exercises.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from aria import config
from aria.models import Decision, PortfolioState
from aria.execution.twak_client import TwakClient, TwakError
from aria.state.db import Store

log = logging.getLogger("aria.execution")

_client: Optional[TwakClient] = None
_wallet_bound = False


async def get_twak() -> TwakClient:
    global _client, _wallet_bound
    if _client is None:
        _client = TwakClient()
    if not _client.running:
        await _client.start()
        _wallet_bound = False  # reset on restart so we re-bind
    if not _wallet_bound:
        try:
            status = await _client.call("get_wallet_status")
            log.info("TWAK wallet status: %s", status)
            mode = status.get("mode") or status.get("walletMode") or str(status) if isinstance(status, dict) else str(status)
            if "not_bound" in str(status).lower() or "unbound" in str(status).lower():
                log.warning("TWAK wallet not bound — swaps will fail. Check wallet.json on Railway.")
            else:
                _wallet_bound = True
                log.info("TWAK wallet ready: %s", mode)
        except TwakError as exc:
            log.warning("get_wallet_status failed: %s", exc)
    return _client


class ExecutionResult:
    def __init__(self, status: str, detail: str = ""):
        self.status = status          # executed | skipped | failed
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.status}:{self.detail}" if self.detail else self.status


def _live() -> bool:
    return config.EXECUTION_MODE == "live" and config.NETWORK == "mainnet"


# --- Quote gate ----------------------------------------------------------------

def check_quote(quote: dict) -> Optional[str]:
    """Pure: returns a rejection reason, or None if the quote is acceptable."""
    if not quote or quote.get("success") is False:
        return f"quote failed: {str(quote)[:200]}"
    impact_raw = str(quote.get("priceImpact", "")).replace("%", "").strip()
    try:
        impact = abs(float(impact_raw))
    except ValueError:
        return f"unparseable priceImpact: {quote.get('priceImpact')!r}"
    if impact > config.MAX_PRICE_IMPACT_PCT:
        return f"price impact {impact}% > max {config.MAX_PRICE_IMPACT_PCT}%"
    return None


def parse_amount(s: object) -> tuple[float, str]:
    """'0.005937 ETH' -> (0.005937, 'ETH'). Raises on garbage."""
    parts = str(s).strip().split()
    return float(parts[0]), (parts[1] if len(parts) > 1 else "")


# --- Swap primitive --------------------------------------------------------------

def _token_ref(symbol: str) -> str:
    """Resolve a token symbol to its BSC contract address for swaps. TWAK's swap
    aggregator only recognizes ~5 tokens by bare symbol (ATOM/AVAX/DOGE/ETH/LTC) and
    returns TOKEN_NOT_FOUND for the rest (XRP/ADA/LINK/UNI/...) — but routes ALL of
    them correctly by contract address (probed 2026-06-22). So always pass the address
    when we have one; fall back to the bare symbol otherwise."""
    return _BSC_CONTRACTS.get(symbol.upper(), symbol)


async def _swap(store: Store, cycle_id: str, kind: str,
                from_token: str, to_token: str, amount: str,
                stop_loss_pct: Optional[float] = None,
                target_pct: Optional[float] = None) -> ExecutionResult:
    """quote -> impact gate -> swap -> log. The only function that moves money.
    stop_loss_pct/target_pct (buys only) are persisted with the live_pos record so the
    exit manager can stop-out / take-profit a position rebuilt from on-chain state."""
    twak = await get_twak()
    base = {"fromChain": config.CHAIN, "toChain": config.CHAIN,
            "fromToken": _token_ref(from_token), "toToken": _token_ref(to_token),
            "amount": amount}
    try:
        quote = await twak.call("get_swap_quote", base)
    except TwakError as exc:
        store.log_trade(cycle_id, kind, from_token, to_token, status="failed",
                        from_amount=amount)
        return ExecutionResult("failed", f"quote error: {exc}")

    reason = check_quote(quote if isinstance(quote, dict) else {})
    if reason:
        store.log_trade(cycle_id, kind, from_token, to_token, status="failed",
                        from_amount=amount)
        return ExecutionResult("failed", f"quote gate: {reason}")

    # TWAK's swap EXECUTION endpoint intermittently returns NETWORK_ERROR ('fetch
    # failed') — confirmed via probe: the SELL quote succeeds but execution flakes. A
    # 'fetch failed' means the request never completed, so the swap did NOT land on
    # chain — retrying is safe (no double-spend). Retry transport errors several times
    # with a short backoff to push the swap through; a revert/validation error (the tx
    # actually reached chain and failed) is NOT retried — recompute next cycle.
    import asyncio as _asyncio
    attempts = 0
    while True:
        attempts += 1
        try:
            result = await twak.call(
                "swap", {**base, "slippage": str(config.SLIPPAGE_PCT)}, timeout=300
            )
            break
        except TwakError as exc:
            msg = str(exc).lower()
            transient = ("fetch failed" in msg or "network_error" in msg
                         or "timeout" in msg or "econn" in msg or "503" in msg or "502" in msg)
            if not transient or attempts >= config.SWAP_MAX_ATTEMPTS:
                from aria import alerts
                await alerts.send(f"❌ swap FAILED after {attempts} attempts: "
                                  f"{from_token}->{to_token} {amount}: {str(exc)[:200]}")
                store.log_trade(cycle_id, kind, from_token, to_token,
                                status="failed", from_amount=amount)
                return ExecutionResult("failed", f"swap error after {attempts} attempts: {exc}")
            backoff = min(2.0 * attempts, 8.0)
            log.warning("swap attempt %d failed (transient: %s) — retrying in %.0fs",
                        attempts, str(exc)[:80], backoff)
            await _asyncio.sleep(backoff)

    detail: dict[str, Any] = result if isinstance(result, dict) else {"raw": str(result)}
    # Swap result shape: {success, txHash, summary:"X TOK -> Y TOK", provider, explorer}
    # Quote shape (get_swap_quote): {success, input:"X TOK", output:"Y TOK", ...}
    # Normalise: prefer summary; fall back to input/output for forward-compat.
    summary = detail.get("summary", "")
    parts = summary.split(" -> ") if " -> " in summary else []
    in_str = parts[0] if len(parts) == 2 else str(detail.get("input", amount))
    out_str = parts[1] if len(parts) == 2 else str(detail.get("output", ""))
    tx_hash = str(detail.get("txHash") or detail.get("hash") or "")

    # A real on-chain swap returns a tx hash (and an output amount). SELLs were observed
    # returning an EMPTY result (no tx, no output) that was wrongly treated as success —
    # the position got cleared, the slot freed, and the agent re-bought, churning while
    # the token stayed on-chain and USDT drained. Treat a no-tx, no-output result as a
    # FAILED swap: do NOT clear/record the position. Log the raw result for diagnosis.
    if not tx_hash and not out_str:
        log.warning("SWAP %s -> %s returned NO tx and NO output — treating as FAILED. "
                    "raw result: %s", from_token, to_token, str(detail)[:400])
        store.log_trade(cycle_id, kind, from_token, to_token, status="failed",
                        from_amount=in_str)
        return ExecutionResult("failed", f"swap returned empty (no tx/output): {str(detail)[:150]}")

    store.log_trade(
        cycle_id, kind, from_token, to_token, status="confirmed",
        from_amount=in_str,
        to_amount=out_str,
        tx_hash=tx_hash,
    )
    log.info("SWAP %s -> %s | %s (tx %s)", from_token, to_token, summary or f"{in_str}->{out_str}", tx_hash[:10])

    # Track live positions in DB so reconcile_portfolio can see them without
    # needing on-chain contract addresses for every possible token.
    if kind == "strategy":
        if to_token not in config.STABLES and from_token in config.STABLES:
            # Confirmed buy: record position
            try:
                import json as _json
                out_amount, _ = parse_amount(out_str)
                in_amount, _ = parse_amount(in_str)
                entry_price = (in_amount / out_amount) if out_amount > 0 else 0.0
                existing = store.get_state(f"live_pos:{to_token}")
                now_iso = datetime.now(timezone.utc).isoformat()
                if existing:
                    prev = _json.loads(existing)
                    total_amt = prev["amount"] + out_amount
                    avg_price = ((prev["amount"] * prev["entry_price"]) + (out_amount * entry_price)) / total_amt if total_amt else entry_price
                    rec = {"amount": total_amt, "entry_price": avg_price,
                           "cost_basis": float(prev.get("cost_basis") or 0.0) + in_amount,  # USD spent, accumulated
                           "stop_loss_pct": stop_loss_pct if stop_loss_pct is not None else prev.get("stop_loss_pct"),
                           "target_pct": target_pct if target_pct is not None else prev.get("target_pct"),
                           "opened_at": prev.get("opened_at") or now_iso}  # keep original open time
                else:
                    rec = {"amount": out_amount, "entry_price": entry_price,
                           "cost_basis": in_amount,  # USD spent on this position
                           "stop_loss_pct": stop_loss_pct, "target_pct": target_pct,
                           "opened_at": now_iso}
                store.set_state(f"live_pos:{to_token}", _json.dumps(rec))
                log.info("live_pos recorded: %s amount=%.6f entry=%.4f stop=%s target=%s",
                         to_token, out_amount, entry_price, stop_loss_pct, target_pct)
            except Exception as exc:
                log.warning("failed to record live_pos for %s: %s", to_token, exc)
        elif from_token not in config.STABLES and to_token in config.STABLES:
            # Confirmed sell: clear position
            store.clear_state(f"live_pos:{from_token}")
            log.info("live_pos cleared: %s", from_token)

    return ExecutionResult("executed", summary or f"{in_str} -> {out_str}")


async def preflight_route(from_token: str, to_token: str, amount_usd: float) -> "tuple[bool, str]":
    """Cheap routability check BEFORE the LLM judge: can this swap be quoted and does
    it pass the price-impact gate? Lets the loop skip un-routable tokens (e.g. BCH/ADA
    with thin BSC liquidity) WITHOUT paying for an LLM judgment that would only fail at
    swap time. A quote is ~free vs an LLM call. No-op (always OK) outside live mode."""
    if not _live():
        return True, ""
    twak = await get_twak()
    base = {"fromChain": config.CHAIN, "toChain": config.CHAIN,
            "fromToken": _token_ref(from_token), "toToken": _token_ref(to_token),
            "amount": f"{amount_usd:.2f}"}
    try:
        quote = await twak.call("get_swap_quote", base)
    except TwakError as exc:
        return False, f"no route: {str(exc)[:120]}"
    reason = check_quote(quote if isinstance(quote, dict) else {})
    return (reason is None), (reason or "")


# --- Decision execution ---------------------------------------------------------

async def execute(decision: Decision, portfolio: PortfolioState, store: Store,
                  dry_run: bool = True) -> ExecutionResult:
    if decision.action == "hold":
        return ExecutionResult("skipped", "hold")
    if config.EXECUTION_MODE == "paper":
        from aria.execution import paper
        return paper.simulate(store, decision, portfolio.total_value_usd)
    if dry_run or not _live():
        return ExecutionResult(
            "skipped", f"dry_run={dry_run} mode={config.EXECUTION_MODE} net={config.NETWORK}"
        )

    if decision.action == "buy":
        amount_usd = portfolio.total_value_usd * decision.size_pct / 100.0
        # Cap at 90% of available USDT so gas always has headroom
        amount_usd = min(amount_usd, portfolio.stable_balance_usd * 0.90)
        if amount_usd < 0.10:
            return ExecutionResult("skipped", f"insufficient USDT balance for min trade (have ${portfolio.stable_balance_usd:.2f})")
        return await _swap(store, decision.cycle_id, "strategy",
                           "USDT", decision.token_symbol, f"{amount_usd:.2f}",
                           stop_loss_pct=decision.stop_loss_pct,
                           target_pct=decision.target_pct)

    if decision.action == "sell":
        pos = next((p for p in portfolio.positions
                    if p.token_symbol == decision.token_symbol), None)
        if pos is None:
            return ExecutionResult("skipped", f"no position in {decision.token_symbol}")
        return await _swap(store, decision.cycle_id, "strategy",
                           pos.token_symbol, "USDT", str(pos.amount))

    if decision.action == "close_all":
        if not portfolio.positions:
            return ExecutionResult("skipped", "no positions to close")
        outcomes = []
        for pos in portfolio.positions:
            r = await _swap(store, decision.cycle_id, "strategy",
                            pos.token_symbol, "USDT", str(pos.amount))
            outcomes.append(f"{pos.token_symbol}:{r.status}")
        status = "executed" if all(o.endswith("executed") for o in outcomes) else "failed"
        return ExecutionResult(status, ",".join(outcomes))

    return ExecutionResult("skipped", f"unknown action {decision.action}")


async def compliance_roundtrip(amount_usd: float, store: Store, cycle_id: str,
                               dry_run: bool = True) -> ExecutionResult:
    """USDT->ETH->USDT heartbeat (competition daily-trade rule). Small,
    directionless, allowed even while halted."""
    if config.EXECUTION_MODE == "paper":
        from aria.execution import paper
        return paper.compliance_roundtrip(store, cycle_id, amount_usd)
    if dry_run or not _live():
        return ExecutionResult("skipped", f"dry_run heartbeat ${amount_usd:.2f}")
    leg1 = await _swap(store, cycle_id, "compliance", "USDT", "ETH", f"{amount_usd:.2f}")
    if leg1.status != "executed":
        return leg1
    try:
        eth_amount, _ = parse_amount(leg1.detail.split("->")[-1])
    except (ValueError, IndexError):
        return ExecutionResult("executed", f"leg1 only ({leg1.detail}); leg2 next cycle")
    leg2 = await _swap(store, cycle_id, "compliance", "ETH", "USDT", f"{eth_amount}")
    return ExecutionResult(leg2.status, f"roundtrip: {leg1.detail} | {leg2.detail}")


# BSC contract addresses for tokens we actively hold.
# get_token_holdings returns empty on this wallet; get_balance with explicit
# contract addresses is the reliable fallback (probed 2026-06-21).
_BSC_CONTRACTS: dict[str, str] = {
    "USDT": "0x55d398326f99059fF775485246999027B3197955",
    "ETH":  "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "LTC":  "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94",
    "XRP":  "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBe",
    "ADA":  "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47",
    "DOGE": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
    "DOT":  "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402",
    "LINK": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    "ATOM": "0x0Eb3a705fc54725037CC9e008bDede697f62F335",
    "UNI":  "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    "ETC":  "0x3d6545b08693daE087E957cb1180ee38B9e3c25E",
    "BCH":  "0x8fF795a6F4D97E7887C79beA79aba5cc76444aDf",
    "SHIB": "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D",
    "CAKE": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "AVAX": "0x1CE0c2827e2eF14D5C4f29a091d735A204794041",
    "AAVE": "0xfb6115445Bff7b52FeB98650C87f44907E58f802",
    "BTT":  "0x352Cb5E19b12FC216548a2677bD0fce83BaE434B",
}


async def _onchain_holdings_usd(twak: "TwakClient", store: Store) -> dict:
    """symbol -> USD value of the wallet's on-chain holding, read straight from
    get_balance's `amounts.totalInFiat` (TWAK returns the fiat value directly, so NO
    decimals math — Binance-Peg DOGE is 8 decimals, most others 18, but totalInFiat
    sidesteps all of it). Queries the whole tradeable set concurrently (bounded) so the
    cycle stays fast. Each value is cached per token; on a transient query error we fall
    back to the last cached value so one network blip never collapses the portfolio
    total (which previously caused a false drawdown halt)."""
    import asyncio as _asyncio

    sem = _asyncio.Semaphore(6)  # don't overwhelm the stdio pipe with 16 at once

    async def one(sym: str, addr: str) -> "tuple[str, float]":
        async with sem:
            try:
                r = await twak.call("get_balance", {
                    "address": config.AGENT_WALLET, "chain": config.CHAIN,
                    "tokenAddress": addr,
                })
                fiat = r.get("amounts", {}).get("totalInFiat") if isinstance(r, dict) else None
                usd = float(fiat) if fiat not in (None, "") else 0.0
                store.set_state(f"onchain_usd:{sym}", str(usd))
                return sym, usd
            except Exception as exc:  # noqa: BLE001
                cached = store.get_state(f"onchain_usd:{sym}")
                if cached is not None:
                    log.warning("get_balance %s failed (%s) — using cached $%s",
                                sym, str(exc)[:50], cached)
                    return sym, float(cached)
                log.warning("get_balance %s failed (%s), no cache — $0", sym, str(exc)[:50])
                return sym, 0.0

    results = await _asyncio.gather(*[one(s, a) for s, a in _BSC_CONTRACTS.items()])
    return {s: v for s, v in results}


# --- Portfolio reconciliation (startup + every cycle in live mode) ----------------

async def reconcile_portfolio(store: Store,
                              prices: Optional[dict[str, float]] = None) -> PortfolioState:
    """On-chain truth -> PortfolioState. Never trust stale local state.
    Token USD values come from `prices` (symbol -> usd, from the signals layer);
    stables count at $1. Unpriced tokens are logged and valued at 0 (conservative
    for drawdown purposes)."""
    from datetime import datetime, timezone
    from aria.models import Position

    twak = await get_twak()
    prices = prices or {}

    # PORTFOLIO VALUE — authoritative, straight from on-chain holdings (totalInFiat).
    # This is the actual wallet value, so drawdown can't be faked by stale local state.
    holdings_usd = await _onchain_holdings_usd(twak, store)
    stable_usd = sum(v for s, v in holdings_usd.items() if s in config.STABLES)
    token_usd = sum(v for s, v in holdings_usd.items() if s not in config.STABLES)
    total = stable_usd + token_usd

    # POSITIONS LIST — built from ACTUAL on-chain holdings so it MATCHES the wallet
    # (the old approach listed only live_pos, which drifted when sells failed silently,
    # making the dashboard show fewer positions than really held and letting the agent
    # over-buy past its concurrent cap). Each holding is enriched with its live_pos
    # metadata (entry/stop/target/opened_at) when tracked; holdings NOT in live_pos
    # ("orphans" from earlier failed sells) are ADOPTED — we write a live_pos for them
    # (entry=current price, default stops, opened_at=now) so the exit manager can manage
    # and eventually consolidate them. amount is derived decimals-free as usd / price.
    import json as _json
    live: dict[str, dict] = {}
    for key, val in store.conn.execute(
            "SELECT key, value FROM agent_state WHERE key LIKE 'live_pos:%'").fetchall():
        try:
            live[key.split(":", 1)[1].upper()] = _json.loads(val)
        except Exception:  # noqa: BLE001
            pass

    positions: list[Position] = []
    for sym, usd in holdings_usd.items():
        if sym in config.STABLES or usd < config.POSITION_MIN_USD:
            continue
        price = prices.get(sym)
        lp = live.get(sym)
        entry = float(lp["entry_price"]) if (lp and lp.get("entry_price")) else None
        # Self-heal a corrupt recorded entry (BNB-priced ~$590 from the old symbol bug).
        if price and entry and (entry > 20 * price or price > 20 * entry):
            store.clear_state(f"live_pos:{sym}")
            lp, entry = None, None
        if price is None:
            price = entry  # unpriced: fall back to recorded entry
        if not price or price <= 0:
            continue
        # Decimals-free amount: on-chain USD value / unit price. 0.999 margin so a later
        # full-exit sell can't exceed the actual balance (avoids insufficient-funds).
        amount = (usd / price) * 0.999
        if lp is None:
            # Adopt the orphan: persist a live_pos so it's tracked AND gets a real
            # opened_at — otherwise the time-stop never fires and it's stuck forever.
            # cost_basis = current value -> the adopted position starts at 0% gain.
            now_iso = datetime.now(timezone.utc).isoformat()
            store.set_state(f"live_pos:{sym}", _json.dumps({
                "amount": amount, "entry_price": price, "cost_basis": usd,
                "stop_loss_pct": config.MR_STOP_LOSS_PCT,
                "target_pct": config.MR_TARGET_PCT, "opened_at": now_iso}))
            log.info("reconcile: adopted orphan holding %s ($%.2f) into tracking", sym, usd)
            lp = {"opened_at": now_iso, "cost_basis": usd}
            entry = price
        opened = lp.get("opened_at")
        try:
            opened_at = datetime.fromisoformat(opened) if opened else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            opened_at = datetime.now(timezone.utc)
        sl = lp.get("stop_loss_pct")
        tp = lp.get("target_pct")
        cost_basis = float(lp["cost_basis"]) if lp.get("cost_basis") else None
        positions.append(Position(
            token_symbol=sym, amount=amount, entry_price_usd=entry or price,
            opened_at=opened_at,
            stop_loss_pct=sl if sl is not None else config.MR_STOP_LOSS_PCT,
            target_pct=tp if tp is not None else config.MR_TARGET_PCT,
            cost_basis_usd=cost_basis,        # USDT spent (fresh, decimals-free PnL basis)
            current_value_usd=usd,            # on-chain totalInFiat — always fresh
        ))

    # Guard against a transient query failure reading the portfolio as near-zero. If the
    # USDT value came back 0 (a blip — the agent always holds meaningful USDT), fall back
    # to the last known good so reconcile never reports a bogus collapse that false-trips
    # the circuit breaker. (Per-token caching in _onchain_holdings_usd already covers most
    # of this; this is the belt-and-suspenders on the stable leg specifically.)
    if stable_usd <= 0:
        last_good = float(store.get_state("last_good_stable_usd") or 0.0)
        if last_good > 0:
            log.warning("reconcile: stable read 0 — using last good stable $%.2f", last_good)
            stable_usd = last_good
            total += last_good
    elif stable_usd > 0:
        store.set_state("last_good_stable_usd", str(stable_usd))

    # High-water mark lives in the DB so drawdown survives restarts
    prev_peak = float(store.get_state("peak_value_usd") or 0.0)
    peak = max(prev_peak, total)
    if peak > prev_peak:
        store.set_state("peak_value_usd", str(peak))

    return PortfolioState(
        timestamp=datetime.now(timezone.utc),
        total_value_usd=total,
        peak_value_usd=peak,
        positions=positions,
        stable_balance_usd=stable_usd,
        trades_today=store.trades_today_utc(),
    )
