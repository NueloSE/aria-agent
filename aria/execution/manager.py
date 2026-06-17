"""Open-position management — runs every cycle BEFORE the brain, deterministically.

For each open position: mark to the latest price, update the peak gain, and exit
on whichever fires first — take-profit at target, the stepped trailing stop (locks
gains once armed), or the hard stop-loss. This is what lets ARIA bank winners and
cut losers instead of only exiting on a regime flip. The brain is not consulted;
this is pure risk management, like the circuit breaker.
"""
from __future__ import annotations

import logging

from aria import config, safety
from aria.models import Decision, PortfolioState
from aria.state.db import Store

log = logging.getLogger("aria.execution.manager")


def _exit_reason(gain: float, peak: float, target: "float | None",
                 stop_loss: "float | None") -> "str | None":
    """Pure decision: which exit (if any) fires. Order: take-profit, trail, stop."""
    if target is not None and gain >= target:
        return "take_profit"
    trail = safety.trailing_stop_for(peak)
    if trail is not None and gain <= trail:
        return "trailing_stop"
    if stop_loss is not None and gain <= -stop_loss:
        return "stop_loss"
    return None


async def manage_open_positions(portfolio: PortfolioState, prices: dict[str, float],
                                store: Store, dry_run: bool) -> list[str]:
    """Returns a list of human-readable exit notes (for logging)."""
    from aria.execution import execute  # avoid import cycle

    notes: list[str] = []
    for pos in portfolio.positions:
        price = prices.get(pos.token_symbol)
        if price is None or price <= 0:
            continue
        gain = pos.gain_pct(price)
        peak = max(pos.peak_gain_pct, gain)
        if peak > pos.peak_gain_pct and config.EXECUTION_MODE == "paper":
            store.paper_position_peak(pos.token_symbol, peak)

        reason = _exit_reason(gain, peak, pos.target_pct, pos.stop_loss_pct)
        if reason is None:
            continue

        decision = Decision(
            regime="high_risk", mode="preservation", action="sell",
            token_symbol=pos.token_symbol, confidence=1.0,
            reasoning=f"EXIT {pos.token_symbol}: {reason} "
                      f"(gain {gain:+.2f}%, peak {peak:+.2f}%, "
                      f"target {pos.target_pct}, stop {pos.stop_loss_pct})",
        )
        store.log_decision(decision, safety_verdict=f"managed_exit:{reason}")
        result = await execute(decision, portfolio, store, dry_run=dry_run)
        store.set_outcome(decision.cycle_id, str(result))
        # cooldown: don't let the next cycle immediately re-buy what we just exited
        from datetime import datetime, timedelta, timezone
        until = (datetime.now(timezone.utc)
                 + timedelta(minutes=config.REENTRY_COOLDOWN_MIN)).isoformat()
        store.set_cooldown(pos.token_symbol, until)
        note = f"{pos.token_symbol} {reason} @ {gain:+.2f}% -> {result.status}"
        notes.append(note)
        log.info("MANAGED EXIT %s", note)
    return notes
