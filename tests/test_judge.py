"""Entry judge (LLM-as-judge) + deterministic entry scan + decision fusion."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aria import brain, config
from aria.main import _entry_decision
from aria.models import EntryJudgment, MarketSnapshot, PortfolioState
from aria.regime import derive_posture
from aria.strategies.base import Proposal

NOW = datetime.now(timezone.utc)


def snap(fg=50, quotes=None) -> MarketSnapshot:
    return MarketSnapshot(timestamp=NOW, fear_greed_index=fg, token_quotes=quotes or {})


def flat() -> PortfolioState:
    return PortfolioState(timestamp=NOW, total_value_usd=100.0, peak_value_usd=100.0,
                          stable_balance_usd=100.0)


def candidate(size=10.0) -> Proposal:
    return Proposal(action="buy", token_symbol="LDO", size_pct=size,
                    stop_loss_pct=5.0, target_pct=7.0, rationale="oversold reclaim")


class TestMockJudge:
    async def test_approves_in_healthy_market(self):
        j = await brain.judge_entry(candidate(), snap(fg=55), flat(),
                                    derive_posture(snap(fg=55)))
        assert j.approve and j.confidence >= config.CONFIDENCE_FLOOR

    async def test_rejects_in_extreme_fear(self):
        j = await brain.judge_entry(candidate(), snap(fg=10), flat(),
                                    derive_posture(snap(fg=10)))
        assert not j.approve


class TestEntryFusion:
    def test_judge_trims_size_never_raises(self):
        j = EntryJudgment(approve=True, confidence=0.7, size_pct=4.0, reasoning="trim")
        d = _entry_decision(candidate(size=10.0), "mean_reversion", j,
                            derive_posture(snap(fg=55)))
        assert d.size_pct == 4.0  # judge's smaller size wins

    def test_posture_multiplier_scales_size(self):
        j = EntryJudgment(approve=True, confidence=0.7, reasoning="ok")
        cautious = derive_posture(snap(fg=22))  # size_multiplier 0.5
        d = _entry_decision(candidate(size=10.0), "mean_reversion", j, cautious)
        assert d.size_pct == pytest.approx(5.0)

    def test_carries_target_and_stop_for_fee_gate(self):
        j = EntryJudgment(approve=True, confidence=0.8, reasoning="ok")
        d = _entry_decision(candidate(), "mean_reversion", j, derive_posture(snap(fg=55)))
        assert d.target_pct == 7.0 and d.stop_loss_pct == 5.0
        assert d.action == "buy" and d.token_symbol == "LDO"


class TestScanEntries:
    async def test_mean_reversion_candidate_found(self, monkeypatch):
        from aria import strategies
        from aria.strategies import mean_reversion

        monkeypatch.setattr(mean_reversion, "propose",
                            lambda s, p, skip=None: candidate())
        prop, mode = await strategies.scan_entries(snap(), flat(), allow_narrative=False)
        assert prop.action == "buy" and mode == "mean_reversion"

    async def test_no_setup_returns_hold(self, monkeypatch):
        from aria import strategies
        from aria.strategies import mean_reversion
        from aria.strategies.base import hold_proposal

        monkeypatch.setattr(mean_reversion, "propose",
                            lambda s, p, skip=None: hold_proposal("nothing washed out"))
        prop, mode = await strategies.scan_entries(snap(), flat(), allow_narrative=False)
        assert prop.action == "hold" and mode is None
