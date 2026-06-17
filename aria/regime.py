"""Global risk posture + cached macro read.

The fast loop polls quotes every ~30s (cheap, 1 credit) but the macro picture
(Fear & Greed, BTC dominance, altcoin season, trending narratives) is the expensive
multi-call fetch — so we read it on a slower cadence (MACRO_REFRESH_SEC) and cache it.

From that cached macro read we derive a coarse, DETERMINISTIC `RiskPosture`: a blunt
global stance the loop consults BEFORE spending an LLM call. The LLM is the nuanced
per-trade judge; this is just "is the whole market too dangerous to add any risk?".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from aria import config
from aria.models import MarketSnapshot

log = logging.getLogger("aria.regime")


@dataclass
class RiskPosture:
    allow_new_entries: bool   # False -> skip the entry scan entirely (no LLM call)
    allow_narrative: bool     # False -> mean-reversion (counter-trend) only
    size_multiplier: float    # scales the gate's proposed size (1.0 / 0.5 / 0.0)
    label: str                # risk_on | neutral | cautious | risk_off
    reason: str


def derive_posture(snapshot: Optional[MarketSnapshot]) -> RiskPosture:
    """Pure function: cached macro snapshot -> coarse global stance."""
    if snapshot is None:
        # No macro read yet — neutral but allow MR only (conservative until we know).
        return RiskPosture(True, False, 0.5, "neutral", "no macro read yet")

    fg = snapshot.fear_greed_index
    m7 = snapshot.total_mcap_change_7d_pct

    # Dangerous macro: do not add ANY new risk (mechanical exits still run).
    if (fg is not None and fg <= config.POSTURE_EXTREME_FEAR) or \
       (m7 is not None and m7 <= config.POSTURE_CRASH_7D_PCT):
        return RiskPosture(
            False, False, 0.0, "risk_off",
            f"extreme fear / crash (F&G={fg}, mcap_7d={m7}) — no new entries",
        )

    # Cautious: counter-trend mean-reversion only, half size.
    if (fg is not None and fg <= config.POSTURE_CAUTION_FEAR) or \
       (m7 is not None and m7 <= config.POSTURE_SOFT_7D_PCT):
        return RiskPosture(
            True, False, 0.5, "cautious",
            f"soft macro (F&G={fg}, mcap_7d={m7}) — mean-reversion only, half size",
        )

    # Healthy: full risk-on, both plays.
    if fg is not None and 40 <= fg <= 80:
        return RiskPosture(True, True, 1.0, "risk_on",
                           f"healthy sentiment (F&G={fg}, mcap_7d={m7})")

    # Anything else (e.g. greed extreme >80, or unknown F&G): neutral, both plays,
    # full size — the per-trade LLM judge handles the nuance from here.
    return RiskPosture(True, True, 1.0, "neutral",
                       f"neutral macro (F&G={fg}, mcap_7d={m7})")


class RegimeCache:
    """Holds the last full macro snapshot + derived posture, refreshing on cadence.

    `snapshot.token_quotes` is kept fresh between macro refreshes by the fast loop
    (cheap, in-memory) so the LLM entry-judge always sees current prices on top of a
    recent macro read."""

    def __init__(self) -> None:
        self.snapshot: Optional[MarketSnapshot] = None
        self.posture: RiskPosture = derive_posture(None)
        self.fetched_at: Optional[datetime] = None

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        if self.snapshot is None or self.fetched_at is None:
            return True
        now = now or datetime.now(timezone.utc)
        return (now - self.fetched_at).total_seconds() >= config.MACRO_REFRESH_SEC

    async def refresh_if_stale(self) -> bool:
        """Fetch a fresh macro snapshot if the cache has expired. Returns True if it
        refreshed (so the caller knows it's safe to run the trend/narrative scan).
        A fetch failure leaves the previous (possibly stale) read in place — never
        crashes the loop; the next tick retries."""
        if not self.is_stale():
            return False
        from aria.signals import client as signals  # lazy — avoids import cycle
        try:
            snap = await signals.fetch_snapshot()
        except Exception as exc:  # noqa: BLE001 — keep last good read, retry next tick
            log.warning("macro refresh failed (keeping last read): %s", exc)
            return False
        self.snapshot = snap
        self.posture = derive_posture(snap)
        self.fetched_at = datetime.now(timezone.utc)
        log.info("macro refreshed | posture=%s (%s)", self.posture.label, self.posture.reason)
        return True

    def update_quotes(self, quotes: dict[str, dict]) -> None:
        """Splice the fast loop's fresh quotes onto the cached macro snapshot so the
        entry-judge sees current prices without a macro re-fetch."""
        if self.snapshot is not None and quotes:
            self.snapshot.token_quotes.update(quotes)
