"""ARIA agent — decoupled two-speed loop.

The FAST loop (every POLL_INTERVAL_SEC, no LLM) does all the time-critical work:
  fetch quotes -> record -> manage exits (take-profit/trailing/stop) -> breaker ->
  refresh macro posture (cached) -> scan deterministic entry gates.
The LLM is event-driven: it is called ONLY when a gate surfaces an entry candidate,
to APPROVE/REJECT it (the "LLM as judge" model). Exits and the circuit breaker are
always mechanical and never wait on the model.

Cadence is adaptive: poll fast while holding (exits need it), slower while flat
(entry signals barely move in 30s) — this also keeps CMC credit burn in budget.

Usage:
  python -m aria.main --dry-run            # one fast tick, no execution
  python -m aria.main --dry-run --loop     # continuous two-speed loop
  python -m aria.main --clear-halt         # human-only: release the drawdown halt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aria import brain, config, execution, safety, strategies
from aria.execution import manager
from aria.models import Decision, PortfolioState, hold_decision
from aria.regime import RegimeCache, RiskPosture
from aria.safety import compliance, window
from aria.signals import client as signals
from aria.state.db import Store

log = logging.getLogger("aria")


async def load_portfolio(store: Store, prices: "dict[str, float] | None" = None) -> PortfolioState:
    """live: reconcile against on-chain holdings via twak (never trust stale local
    state). paper: mark the simulated book to the accumulated prices. stub: synthetic
    flat portfolio for offline development."""
    if config.EXECUTION_MODE == "live":
        return await execution.reconcile_portfolio(store, prices or {})
    if config.EXECUTION_MODE == "paper":
        from aria.execution import paper
        return paper.load_state(store)
    now = datetime.now(timezone.utc)
    return PortfolioState(
        timestamp=now,
        total_value_usd=100.0,
        peak_value_usd=100.0,
        stable_balance_usd=100.0,
    )


async def maybe_heartbeat(store: Store, portfolio: PortfolioState, dry_run: bool,
                          cycle_id: str) -> None:
    """Competition daily-trade rule. Outside LLM control; runs even while HALTED and
    even on signal-failure ticks — going silent for a day is a rule violation.
    Only an explicit emergency stop (override='off') suppresses it; the competition
    window gate and 'no-window-configured' denial apply to strategy trades, not here."""
    if store.get_state(window.KEY_OVERRIDE) == "off":
        return
    trades_today = store.trades_today_utc()
    if not compliance.heartbeat_due(trades_today=trades_today):
        return
    amount = compliance.heartbeat_amount_usd(portfolio.total_value_usd)
    result = await execution.compliance_roundtrip(amount, store, cycle_id, dry_run=dry_run)
    if result.status != "executed":
        frm, to = compliance.COMPLIANCE_PAIR
        store.log_trade(cycle_id, "compliance", frm, to, status=str(result),
                        from_amount=f"{amount:.2f}")
    log.info("compliance heartbeat (%d trades today): %s", trades_today, result)


def _persist_regime(store: Store, regime: RegimeCache, posture: RiskPosture) -> None:
    """Mirror the in-memory posture + macro read to agent_state so the dashboard
    (a separate read-only process) can show what ARIA is currently seeing."""
    snap = regime.snapshot
    store.set_state("regime", json.dumps({
        "posture": posture.label,
        "reason": posture.reason,
        "allow_new_entries": posture.allow_new_entries,
        "size_multiplier": posture.size_multiplier,
        "fear_greed": snap.fear_greed_index if snap else None,
        "fear_greed_label": snap.fear_greed_label if snap else None,
        "mcap_7d": snap.total_mcap_change_7d_pct if snap else None,
        "updated": datetime.now(timezone.utc).isoformat(),
    }))


def _has_room(portfolio: PortfolioState) -> bool:
    """Can we open another position? Need deployable stables and room under the
    concurrent-position cap (each entry is already size-capped at MAX_POSITION_PCT)."""
    if portfolio.stable_balance_usd < config.MIN_DEPLOYED_USD:
        return False
    return len(portfolio.positions) < config.MAX_CONCURRENT_POSITIONS


def _entry_decision(candidate, mode: str, judgment, posture: RiskPosture) -> Decision:
    """Fuse the deterministic candidate with the LLM's verdict + global posture into a
    buy Decision. The judge may TRIM size, never raise it; posture scales it again."""
    size = candidate.size_pct
    if judgment.size_pct is not None:
        size = min(size, judgment.size_pct)
    size = min(size * posture.size_multiplier, config.MAX_POSITION_PCT)
    regime = "trending" if mode in ("narrative_rotation", "breakout") else "ranging"
    return Decision(
        regime=regime, mode=mode, action="buy",
        token_symbol=candidate.token_symbol, size_pct=size,
        stop_loss_pct=candidate.stop_loss_pct, target_pct=candidate.target_pct,
        confidence=judgment.confidence,
        reasoning=f"{candidate.rationale} | judge: {judgment.reasoning}",
    )


async def _force_preservation(store: Store, portfolio: PortfolioState, dry_run: bool,
                              reason: str) -> None:
    from aria import alerts
    await alerts.send(f"⚠️ {reason} — forcing preservation (close to stables) until signals return")
    decision = Decision(regime="high_risk", mode="preservation", action="close_all",
                        confidence=1.0, reasoning=reason)
    store.log_decision(decision, safety_verdict="forced_preservation")
    result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
    store.set_outcome(decision.cycle_id, str(result))
    await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)


async def fast_tick(store: Store, regime: RegimeCache, dry_run: bool,
                    signal_failures: int = 0) -> "tuple[int, bool]":
    """One fast-loop tick. Returns (consecutive-signal-failures, holding?)."""
    # 0a. Halt latch — a halted agent only heartbeats.
    if safety.is_halted(store):
        portfolio = await load_portfolio(store)
        decision = hold_decision(f"HALTED ({safety.halt_reason(store)}) — run --clear-halt to resume")
        store.log_decision(decision, safety_verdict="halted")
        log.warning("agent halted; holding. %s", safety.halt_reason(store))
        await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures, bool(portfolio.positions)

    # 1. Poll quotes — ONE CMC credit. No quotes means no trading.
    try:
        quotes = await signals.fetch_quotes_only()
    except Exception as exc:  # noqa: BLE001 — fail safe, never crash the loop
        signal_failures += 1
        log.error("quote fetch failed (%d consecutive): %s", signal_failures, exc)
        portfolio = await load_portfolio(store)
        if signal_failures >= config.SIGNAL_MAX_CONSECUTIVE_FAILURES:
            await _force_preservation(store, portfolio, dry_run,
                                      f"{signal_failures} consecutive signal failures")
        else:
            decision = hold_decision(f"quote fetch failed: {exc}")
            store.log_decision(decision, safety_verdict="auto_hold")
            await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures, bool(portfolio.positions)

    # 1a. Accumulate the price series (CMC sells no history — we build our own).
    store.record_prices(quotes)
    prices = {s: q["price"] for s, q in quotes.items()
              if isinstance(q.get("price"), (int, float))}

    # 1b. Portfolio — on-chain truth (live), paper book, or stub.
    portfolio = await load_portfolio(store, prices)

    # 1b2. MECHANICAL EXITS FIRST — take-profit / trailing / stop. No LLM, ever.
    if portfolio.positions:
        exits = await manager.manage_open_positions(portfolio, prices, store, dry_run)
        if exits:
            portfolio = await load_portfolio(store, prices)

    # 0b. Circuit breaker — mechanical, brain NOT consulted on a breach.
    # Runs BEFORE the trading-window gate so a drawdown breach always triggers the halt
    # even when the competition window is not yet configured (e.g. live mode, pre-start).
    if safety.check_drawdown(portfolio):
        safety.trigger_halt(store, f"drawdown {portfolio.drawdown_pct:.2f}% >= {config.HALT_DRAWDOWN_PCT}%")
        decision = Decision(regime="high_risk", mode="preservation", action="close_all",
                            confidence=1.0,
                            reasoning=f"CIRCUIT BREAKER: drawdown {portfolio.drawdown_pct:.2f}% — "
                                      "closing everything, halting until manual restart")
        store.log_decision(decision, safety_verdict="halt_triggered")
        result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
        store.set_outcome(decision.cycle_id, str(result))
        await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures, bool(portfolio.positions)

    # 1c. Competition window / operator override.
    allowed, why = window.trading_allowed(store)
    if not allowed:
        decision = hold_decision(f"trading gated: {why}", regime="high_risk")
        store.log_decision(decision, safety_verdict="window_closed")
        store.snapshot_portfolio(portfolio)
        log.info("tick %s | window closed: %s", decision.cycle_id[:8], why)
        return 0, bool(portfolio.positions)

    # 2. Refresh the cached macro read + global posture (slow cadence) and splice in
    #    fresh quotes so the entry judge sees current prices on a recent macro picture.
    refreshed = await regime.refresh_if_stale()
    regime.update_quotes(quotes)
    posture = regime.posture
    _persist_regime(store, regime, posture)

    # 3. ENTRY HUNT — deterministic gates, then the event-driven LLM judge.
    decision = await _hunt_entry(store, regime, portfolio, posture, refreshed)

    # 4. Validate (safety has veto power over everything) + execute.
    try:
        safety.validate(decision, portfolio)
        if decision.action == "buy":
            verdict = "dry_run" if dry_run else "approved"
        else:
            verdict = "no_entry"
    except safety.Veto as veto:
        log.warning("VETO %s", veto)
        decision = hold_decision(f"vetoed: {veto}", regime=decision.regime)
        verdict = f"vetoed:{veto}"

    store.log_decision(decision, safety_verdict=verdict)
    store.snapshot_portfolio(portfolio)
    result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
    store.set_outcome(decision.cycle_id, str(result))

    # 5. Compliance heartbeat (competition rule, independent of strategy).
    await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)

    log.info("tick %s | posture=%s mode=%s action=%s conf=%.2f | %s | %s",
             decision.cycle_id[:8], posture.label, decision.mode, decision.action,
             decision.confidence, verdict, result)

    holding = bool(portfolio.positions) or (decision.action == "buy" and result.status == "executed")
    return 0, holding


async def _hunt_entry(store: Store, regime: RegimeCache, portfolio: PortfolioState,
                      posture: RiskPosture, refreshed: bool) -> Decision:
    """Deterministic entry scan + event-driven LLM judgment. Returns a buy Decision
    only when a gate found a setup AND the LLM approved it; otherwise a logged hold."""
    if not posture.allow_new_entries:
        return hold_decision(f"no new entries (posture={posture.label}: {posture.reason})",
                             regime="ranging")
    if not _has_room(portfolio):
        return hold_decision("portfolio full — no room for a new entry", regime="ranging")
    if regime.snapshot is None:
        return hold_decision("no macro read yet — deferring entries", regime="ranging")

    snap = regime.snapshot
    # Exclude tokens in cooldown (just-exited OR just judge-rejected) so the gate
    # falls through to the best NON-cooled candidate instead of re-judging the same one.
    skip = store.cooled_down_tokens()
    candidate, mode = await strategies.scan_entries(
        snap, portfolio, allow_narrative=(refreshed and posture.allow_narrative), skip=skip)
    if candidate.action != "buy" or not candidate.token_symbol:
        return hold_decision(candidate.rationale, regime="ranging")

    # Per-candidate TECHNICAL confirmation (1 credit on THIS token only): real RSI
    # (oversold for MR / not-overbought for breakout) + Fibonacci target/stop. Fail-safe.
    if config.MR_CONFIRM_ENABLED and mode in ("mean_reversion", "breakout"):
        try:
            from aria.signals import client as signals_mod
            from aria.strategies import confirm
            ta = confirm.parse_ta(await signals_mod.fetch_token_ta(candidate.token_symbol))
            price = (snap.token_quotes.get(candidate.token_symbol) or {}).get("price")
            confirm_fn = (confirm.confirm_candidate if mode == "mean_reversion"
                          else confirm.confirm_breakout)
            ok, reason, candidate = confirm_fn(candidate, ta, price)
            if not ok:
                until = (datetime.now(timezone.utc)
                         + timedelta(minutes=config.REJECT_COOLDOWN_MIN)).isoformat()
                store.set_cooldown(candidate.token_symbol, until)
                return hold_decision(f"TA-rejected {candidate.token_symbol}: {reason}",
                                     regime="ranging")
        except Exception as exc:  # noqa: BLE001 — never let confirmation block the loop
            log.warning("TA confirmation failed (proceeding without): %s", exc)

    # EVENT-DRIVEN LLM CALL — only now that a real, non-cooled candidate exists.
    judgment = await brain.judge_entry(candidate, snap, portfolio, posture)
    if judgment.approve and judgment.confidence >= config.CONFIDENCE_FLOOR:
        return _entry_decision(candidate, mode or "mean_reversion", judgment, posture)
    # Cool the rejected token down so we don't re-pay the judge for it every tick.
    until = (datetime.now(timezone.utc)
             + timedelta(minutes=config.REJECT_COOLDOWN_MIN)).isoformat()
    store.set_cooldown(candidate.token_symbol, until)
    return hold_decision(f"judge rejected {candidate.token_symbol} "
                         f"(conf {judgment.confidence:.2f}): {judgment.reasoning}", regime="ranging")


async def run_cycle(store: Store, dry_run: bool, signal_failures: int = 0) -> int:
    """Back-compat single-tick entry point (used by tests and any external caller).
    Drives one fast_tick with a fresh macro cache so posture is always current."""
    failures, _holding = await fast_tick(store, RegimeCache(), dry_run, signal_failures)
    return failures


async def main() -> None:
    parser = argparse.ArgumentParser(prog="aria")
    parser.add_argument("--dry-run", action="store_true", help="never execute trades")
    parser.add_argument("--loop", action="store_true", help="run the continuous two-speed loop")
    parser.add_argument("--clear-halt", action="store_true",
                        help="human-only: release the drawdown halt and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store(config.DB_PATH)

    if args.clear_halt:
        if safety.is_halted(store):
            safety.clear_halt(store)
            print("halt cleared.")
        else:
            print("agent was not halted.")
        return

    log.info("ARIA starting | network=%s brain=%s/%s exec=%s dry_run=%s | poll=%.0fs/%.0fs macro=%.0fs",
             config.NETWORK, config.BRAIN_MODE, config.BRAIN_MODEL, config.EXECUTION_MODE,
             args.dry_run, config.POLL_INTERVAL_SEC, config.POLL_INTERVAL_FLAT_SEC,
             config.MACRO_REFRESH_SEC)
    if safety.is_halted(store):
        log.warning("starting in HALTED state: %s", safety.halt_reason(store))

    regime = RegimeCache()
    failures = 0
    while True:
        failures, holding = await fast_tick(store, regime, dry_run=args.dry_run,
                                            signal_failures=failures)
        if not args.loop:
            break
        # Adaptive cadence: tight while holding (exit reaction), relaxed while flat.
        interval = config.POLL_INTERVAL_SEC if holding else config.POLL_INTERVAL_FLAT_SEC
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
