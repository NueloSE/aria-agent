"""Global risk posture derivation + macro-cache staleness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aria import config
from aria.models import MarketSnapshot
from aria.regime import RegimeCache, derive_posture


def snap(fg=None, m7=None) -> MarketSnapshot:
    return MarketSnapshot(timestamp=datetime.now(timezone.utc),
                          fear_greed_index=fg, total_mcap_change_7d_pct=m7)


class TestPosture:
    def test_no_snapshot_is_conservative(self):
        p = derive_posture(None)
        assert p.allow_new_entries and not p.allow_narrative and p.size_multiplier == 0.5

    def test_extreme_fear_blocks_entries(self):
        p = derive_posture(snap(fg=10, m7=-2))
        assert not p.allow_new_entries
        assert p.label == "risk_off" and p.size_multiplier == 0.0

    def test_market_crash_blocks_entries(self):
        p = derive_posture(snap(fg=45, m7=-20))
        assert not p.allow_new_entries and p.label == "risk_off"

    def test_soft_macro_is_cautious_mr_only(self):
        p = derive_posture(snap(fg=22, m7=-3))
        assert p.allow_new_entries and not p.allow_narrative
        assert p.size_multiplier == 0.5 and p.label == "cautious"

    def test_healthy_is_risk_on_full_size(self):
        p = derive_posture(snap(fg=55, m7=2))
        assert p.allow_new_entries and p.allow_narrative
        assert p.size_multiplier == 1.0 and p.label == "risk_on"

    def test_greed_extreme_is_neutral_not_blocked(self):
        # >80 greed: not blocked here — the per-trade judge handles the nuance
        p = derive_posture(snap(fg=90, m7=1))
        assert p.allow_new_entries and p.allow_narrative and p.label == "neutral"


class TestRegimeCache:
    def test_starts_stale(self):
        assert RegimeCache().is_stale()

    def test_fresh_after_fetch_then_stale_after_ttl(self, monkeypatch):
        c = RegimeCache()
        c.snapshot = snap(fg=50)
        c.fetched_at = datetime.now(timezone.utc)
        assert not c.is_stale()
        old = datetime.now(timezone.utc) - timedelta(seconds=config.MACRO_REFRESH_SEC + 1)
        c.fetched_at = old
        assert c.is_stale()

    async def test_refresh_failure_keeps_last_read(self, monkeypatch):
        c = RegimeCache()
        c.snapshot = snap(fg=50)
        c.fetched_at = datetime.now(timezone.utc) - timedelta(seconds=config.MACRO_REFRESH_SEC + 1)

        async def boom():
            raise RuntimeError("cmc down")

        from aria.signals import client as signals
        monkeypatch.setattr(signals, "fetch_snapshot", boom)
        refreshed = await c.refresh_if_stale()
        assert refreshed is False
        assert c.snapshot is not None  # previous read preserved

    def test_update_quotes_splices_prices(self):
        c = RegimeCache()
        c.snapshot = snap(fg=50)
        c.update_quotes({"ETH": {"price": 3000.0}})
        assert c.snapshot.token_quotes["ETH"]["price"] == 3000.0
