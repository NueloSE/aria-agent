"""ARIA agent loop: fetch -> reason -> refine -> validate -> execute -> log.

Usage:
  python -m aria.main --dry-run            # one full cycle, no execution
  python -m aria.main --dry-run --loop     # continuous, CYCLE_INTERVAL_MIN apart
  python -m aria.main --clear-halt         # human-only: release the drawdown halt
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from aria import brain, config, execution, safety, strategies
from aria.models import Decision, PortfolioState, hold_decision
from aria.safety import compliance, window
from aria.signals import client as signals
from aria.state.db import Store

log = logging.getLogger("aria")


async def load_portfolio(store: Store, snapshot=None) -> PortfolioState:
    """live: reconcile against on-chain holdings via twak (never trust stale
    local state). paper: mark the simulated book to the accumulated prices.
    stub: synthetic flat portfolio for offline development."""
    if config.EXECUTION_MODE == "live":
        prices: dict[str, float] = {}
        if snapshot is not None:
            for sym, q in snapshot.token_quotes.items():
                price = q.get("price")
                if isinstance(price, (int, float)):
                    prices[sym] = float(price)
        return await execution.reconcile_portfolio(store, prices)
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
    """Competition daily-trade rule. Outside LLM control; runs even while HALTED
    and even on signal-failure cycles — going silent for a day is a rule violation."""
    allowed, _ = window.trading_allowed(store)
    if not allowed:
        return  # the daily-trade rule only exists inside the competition window
    trades_today = store.trades_today_utc()
    if not compliance.heartbeat_due(trades_today=trades_today):
        return
    amount = compliance.heartbeat_amount_usd(portfolio.total_value_usd)
    result = await execution.compliance_roundtrip(amount, store, cycle_id, dry_run=dry_run)
    if result.status != "executed":  # live legs log themselves; record skips/failures
        frm, to = compliance.COMPLIANCE_PAIR
        store.log_trade(cycle_id, "compliance", frm, to, status=str(result),
                        from_amount=f"{amount:.2f}")
    log.info("compliance heartbeat (%d trades today): %s", trades_today, result)


async def run_cycle(store: Store, dry_run: bool, signal_failures: int = 0) -> int:
    """Runs one cycle. Returns the consecutive-signal-failure count (0 on success)."""
    # 0a. Halt latch — checked before anything else; a halted agent only heartbeats
    if safety.is_halted(store):
        portfolio = await load_portfolio(store)
        decision = hold_decision(f"HALTED ({safety.halt_reason(store)}) — "
                                 "run --clear-halt to resume")
        store.log_decision(decision, safety_verdict="halted")
        log.warning("agent halted; holding. %s", safety.halt_reason(store))
        await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures

    # 1. Fetch signals — no signals means no trading (also prices reconciliation)
    try:
        snapshot = await signals.fetch_snapshot()
    except Exception as exc:  # noqa: BLE001 — fail safe, never crash the loop
        signal_failures += 1
        log.error("signal fetch failed (%d consecutive): %s", signal_failures, exc)
        portfolio = await load_portfolio(store)
        if signal_failures >= config.SIGNAL_MAX_CONSECUTIVE_FAILURES:
            from aria import alerts
            await alerts.send(f"⚠️ {signal_failures} consecutive signal failures — "
                              "forcing preservation (close to stables) until signals return")
            # DESIGN.md policy: blind agent goes to stables until signals return
            decision = Decision(
                regime="high_risk", mode="preservation", action="close_all",
                confidence=1.0,
                reasoning=f"{signal_failures} consecutive signal failures — "
                          f"forced preservation (close to stables) until signals return",
            )
            store.log_decision(decision, safety_verdict="forced_preservation")
            result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
            store.set_outcome(decision.cycle_id, str(result))
        else:
            decision = hold_decision(f"signal fetch failed: {exc}")
            store.log_decision(decision, safety_verdict="auto_hold")
        await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures

    # 1a. Accumulate the price series (CMC sells no history — we build our own)
    store.record_prices(snapshot.token_quotes)

    # 1b. Portfolio — on-chain truth (live), paper book, or stub — priced from snapshot
    portfolio = await load_portfolio(store, snapshot)

    # 1c. Competition window / operator override — outside it, observe but never trade
    allowed, why = window.trading_allowed(store)
    if not allowed:
        decision = hold_decision(f"trading gated: {why}", regime="high_risk")
        store.log_decision(decision, signals_json=snapshot.model_dump_json(),
                           safety_verdict="window_closed")
        store.snapshot_portfolio(portfolio)
        log.info("cycle %s | window closed: %s", decision.cycle_id[:8], why)
        return 0

    # 0b. Circuit breaker — brain is NOT consulted on a breach
    if safety.check_drawdown(portfolio):
        safety.trigger_halt(
            store, f"drawdown {portfolio.drawdown_pct:.2f}% >= {config.HALT_DRAWDOWN_PCT}%"
        )
        decision = Decision(
            regime="high_risk", mode="preservation", action="close_all",
            confidence=1.0,
            reasoning=f"CIRCUIT BREAKER: drawdown {portfolio.drawdown_pct:.2f}% — "
                      "closing everything, halting until manual restart",
        )
        store.log_decision(decision, safety_verdict="halt_triggered")
        result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
        store.set_outcome(decision.cycle_id, str(result))
        await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)
        return signal_failures

    # 2. Reason — malformed/broken brain output becomes a hold
    try:
        decision = await brain.decide(snapshot, portfolio, history=store.recent_decisions(5))
    except Exception as exc:  # noqa: BLE001
        log.error("brain failed: %s", exc)
        decision = hold_decision(f"brain failure: {exc}")

    # 2b. Strategy refinement — the mode's gates concretize (or reject) the idea
    try:
        decision = await strategies.refine(decision, snapshot, portfolio)
    except Exception as exc:  # noqa: BLE001
        log.error("strategy refinement failed: %s", exc)
        decision = hold_decision(f"strategy refinement failed: {exc}", regime=decision.regime)

    # refinement may have enriched the snapshot with candidate prices — capture them
    # so a paper/live buy can price its chosen token from this cycle's data
    store.record_prices(snapshot.token_quotes)

    # 3. Validate — safety has veto power over everything
    try:
        safety.validate(decision, portfolio)  # halt latch already handled at step 0a
        verdict = "dry_run" if dry_run else "approved"
    except safety.Veto as veto:
        verdict = f"vetoed:{veto}"
        log.warning("VETO %s", veto)
        decision = hold_decision(f"vetoed: {veto}", regime=decision.regime)

    snapshot_json = snapshot.model_dump_json()
    store.log_decision(decision, signals_json=snapshot_json, safety_verdict=verdict)
    store.snapshot_portfolio(portfolio)

    # 4. Execute
    result = await execution.execute(decision, portfolio, store, dry_run=dry_run)
    store.set_outcome(decision.cycle_id, str(result))

    # 5. Compliance heartbeat (competition rule, independent of strategy)
    await maybe_heartbeat(store, portfolio, dry_run, decision.cycle_id)

    log.info(
        "cycle %s | regime=%s mode=%s action=%s conf=%.2f | %s | %s",
        decision.cycle_id[:8], decision.regime, decision.mode,
        decision.action, decision.confidence, verdict, result,
    )
    log.info("reasoning: %s", decision.reasoning)
    return 0  # success resets the consecutive-failure counter


async def main() -> None:
    parser = argparse.ArgumentParser(prog="aria")
    parser.add_argument("--dry-run", action="store_true", help="never execute trades")
    parser.add_argument("--loop", action="store_true", help="run continuously")
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

    log.info("ARIA starting | network=%s brain=%s/%s dry_run=%s db=%s",
             config.NETWORK, config.BRAIN_MODE, config.BRAIN_MODEL,
             args.dry_run, config.DB_PATH)
    if safety.is_halted(store):
        log.warning("starting in HALTED state: %s", safety.halt_reason(store))

    failures = 0
    while True:
        failures = await run_cycle(store, dry_run=args.dry_run, signal_failures=failures)
        if not args.loop:
            break
        await asyncio.sleep(config.CYCLE_INTERVAL_MIN * 60)


if __name__ == "__main__":
    asyncio.run(main())
