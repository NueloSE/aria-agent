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


async def get_twak() -> TwakClient:
    global _client
    if _client is None:
        _client = TwakClient()
    if not _client.running:
        await _client.start()
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

async def _swap(store: Store, cycle_id: str, kind: str,
                from_token: str, to_token: str, amount: str) -> ExecutionResult:
    """quote -> impact gate -> swap -> log. The only function that moves money."""
    twak = await get_twak()
    base = {"fromChain": config.CHAIN, "toChain": config.CHAIN,
            "fromToken": from_token, "toToken": to_token, "amount": amount}
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

    attempts = 0
    while True:
        attempts += 1
        try:
            result = await twak.call(
                "swap", {**base, "slippage": str(config.SLIPPAGE_PCT)}, timeout=300
            )
            break
        except TwakError as exc:
            if attempts >= 2:  # max ONE retry
                from aria import alerts
                await alerts.send(f"❌ swap FAILED after retry: {from_token}->{to_token} "
                                  f"{amount}: {str(exc)[:200]}")
                store.log_trade(cycle_id, kind, from_token, to_token,
                                status="failed", from_amount=amount)
                return ExecutionResult("failed", f"swap error after retry: {exc}")
            log.warning("swap attempt %d failed, retrying once: %s", attempts, exc)

    detail: dict[str, Any] = result if isinstance(result, dict) else {"raw": str(result)}
    # Swap result shape: {success, txHash, summary:"X TOK -> Y TOK", provider, explorer}
    # Quote shape (get_swap_quote): {success, input:"X TOK", output:"Y TOK", ...}
    # Normalise: prefer summary; fall back to input/output for forward-compat.
    summary = detail.get("summary", "")
    parts = summary.split(" -> ") if " -> " in summary else []
    in_str = parts[0] if len(parts) == 2 else str(detail.get("input", amount))
    out_str = parts[1] if len(parts) == 2 else str(detail.get("output", ""))
    tx_hash = str(detail.get("txHash") or detail.get("hash") or "")
    store.log_trade(
        cycle_id, kind, from_token, to_token, status="confirmed",
        from_amount=in_str,
        to_amount=out_str,
        tx_hash=tx_hash,
    )
    log.info("SWAP %s -> %s | %s (tx %s)", from_token, to_token, summary or f"{in_str}->{out_str}", tx_hash[:10])
    return ExecutionResult("executed", summary or f"{in_str} -> {out_str}")


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
        return await _swap(store, decision.cycle_id, "strategy",
                           "USDT", decision.token_symbol, f"{amount_usd:.2f}")

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
    holdings = await twak.call(
        "get_token_holdings", {"address": config.AGENT_WALLET, "chain": config.CHAIN}
    )
    items = holdings if isinstance(holdings, list) else holdings.get("tokens", []) \
        if isinstance(holdings, dict) else []

    prices = prices or {}
    stable_usd = 0.0
    positions: list[Position] = []
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol", "")).upper()
        try:
            amount = float(item.get("balance") or item.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        if sym in config.STABLES:
            stable_usd += amount
            total += amount
        else:
            price = prices.get(sym)
            if price is None:
                log.warning("reconcile: no price for %s — valued at 0", sym)
                price = 0.0
            total += amount * price
            positions.append(Position(
                token_symbol=sym, amount=amount, entry_price_usd=price,
                opened_at=datetime.now(timezone.utc),
            ))

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
