"""Daily compliance heartbeat — a COMPETITION RULE, not a strategy.

Rules: minimum 1 trade per day (7 over the week). Admins confirmed ETH/USDT
round-trips count and the daily-trade rule is a qualification constraint, not a
scoring lever. This module decides WHEN the heartbeat is owed; execution performs
a small USDT->ETH->USDT round trip (returns to preservation posture, ~negligible
cost at COMPLIANCE_TRADE_SIZE_PCT of portfolio).

Deliberately outside the LLM's control. Runs even while HALTED — going silent
for a day is a rule violation, and the round trip adds no directional risk.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from aria import config

COMPLIANCE_PAIR = ("USDT", "ETH")   # both on the eligible list; never WBNB (ineligible)


def heartbeat_due(now_utc: Optional[datetime] = None, trades_today: int = 0) -> bool:
    """True when the day is getting old and no trade has happened yet."""
    now = now_utc or datetime.now(timezone.utc)
    return trades_today < config.MIN_TRADES_PER_DAY and now.hour >= config.COMPLIANCE_TRADE_HOUR_UTC


def heartbeat_amount_usd(portfolio_value_usd: float) -> float:
    """Small but not dust: max(size% of portfolio, $1) so the trade registers."""
    return max(portfolio_value_usd * config.COMPLIANCE_TRADE_SIZE_PCT / 100.0, 1.0)
