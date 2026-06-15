"""Safety layer — VETO POWER OVER EVERYTHING, including the LLM.

Two parts:
  - validate(): pure per-decision gates (cheapest first)
  - the HALT LATCH: drawdown breach -> close everything -> persist halted state ->
    refuse all new risk until a human runs --clear-halt. Survives restarts (DB-backed).

Hard rule #7: every path here is unit-tested before any real-money run.
Note on MIN_DEPLOYED: ARIA only ever closes to USDT (eligible, in-scope) and never
transfers value out of the wallet, so the sub-$1-hour rule is satisfied by
construction — there is no code path that empties the portfolio.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aria import config
from aria.models import Decision, PortfolioState
from aria.state.db import Store

log = logging.getLogger("aria.safety")

HALT_KEY = "halted"


class Veto(Exception):
    """Raised when a decision is rejected. Message is logged verbatim."""


# --- Halt latch ---------------------------------------------------------------

def is_halted(store: Store) -> bool:
    return store.get_state(HALT_KEY) is not None


def halt_reason(store: Store) -> str:
    return store.get_state(HALT_KEY) or ""


def trigger_halt(store: Store, reason: str) -> None:
    from aria import alerts  # local import — avoids a cycle at module load

    log.critical("HALT TRIGGERED: %s — manual restart required (--clear-halt)", reason)
    store.set_state(HALT_KEY, f"{datetime.now(timezone.utc).isoformat()} {reason}")
    alerts.send_sync(f"🛑 CIRCUIT BREAKER: {reason}\nAll positions closing; trading halted "
                     f"until you run --clear-halt (or the dashboard button).")


def clear_halt(store: Store) -> None:
    log.warning("halt cleared by human: %s", halt_reason(store))
    store.clear_state(HALT_KEY)


def check_drawdown(portfolio: PortfolioState) -> bool:
    """True if the halt threshold is breached (caller triggers the latch).
    Epsilon guards the boundary: (1 - 80/100)*100 is 19.999999999999996 in IEEE-754 —
    a breaker that misses its own threshold by 4e-15 is not a breaker."""
    return portfolio.drawdown_pct >= config.HALT_DRAWDOWN_PCT - 1e-9


# --- Per-decision gates ---------------------------------------------------------

def validate(decision: Decision, portfolio: PortfolioState, halted: bool = False) -> None:
    """Raises Veto if the decision may not execute.
    While halted: only de-risking (hold/close_all/sell) passes — never new buys."""
    if halted and decision.action == "buy":
        raise Veto("agent is HALTED — buys forbidden until --clear-halt")

    if decision.action in ("hold", "close_all"):
        return  # de-risking and inaction are always allowed

    if decision.confidence < config.CONFIDENCE_FLOOR:
        raise Veto(f"confidence {decision.confidence} below floor {config.CONFIDENCE_FLOOR}")

    if not decision.token_symbol:
        raise Veto(f"action {decision.action} requires token_symbol")

    if decision.token_symbol not in config.ELIGIBLE_SYMBOLS:
        raise Veto(f"{decision.token_symbol} not in official 149-token eligible list")

    if decision.action == "buy":
        if decision.stop_loss_pct is None or decision.stop_loss_pct <= 0:
            raise Veto("buy without a stop_loss_pct")
        if decision.size_pct <= 0:
            raise Veto("buy with size_pct <= 0")
        if check_drawdown(portfolio):
            raise Veto(
                f"drawdown {portfolio.drawdown_pct:.2f}% >= halt threshold "
                f"{config.HALT_DRAWDOWN_PCT}% — no new risk"
            )
