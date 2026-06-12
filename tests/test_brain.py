"""Brain tests — fixtures and canned data only, never live API calls."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aria import config
from aria.brain import decide
from aria.brain.live import parse_brain_output
from aria.brain.prompt import SYSTEM_PROMPT, build_user_message
from aria.models import PortfolioState
from aria.signals.client import fetch_snapshot_from_fixtures


def flat_portfolio(value: float = 100.0, peak: float = 100.0) -> PortfolioState:
    return PortfolioState(
        timestamp=datetime.now(timezone.utc),
        total_value_usd=value,
        peak_value_usd=peak,
        stable_balance_usd=value,
    )


GOOD_OUTPUT = {
    "regime": "trending",
    "mode": "narrative_rotation",
    "action": "buy",
    "token_symbol": "CAKE",
    "size_pct": 10.0,
    "stop_loss_pct": 6.0,
    "confidence": 0.75,
    "reasoning": "test",
}


class TestParseBrainOutput:
    def test_happy_path(self):
        d = parse_brain_output(GOOD_OUTPUT)
        assert d.action == "buy"
        assert d.cycle_id  # runtime-assigned, not model-chosen

    def test_invalid_regime_rejected(self):
        with pytest.raises(Exception):
            parse_brain_output({**GOOD_OUTPUT, "regime": "moon_soon"})

    def test_oversized_position_rejected(self):
        with pytest.raises(Exception):
            parse_brain_output({**GOOD_OUTPUT, "size_pct": config.MAX_POSITION_PCT + 1})

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(Exception):
            parse_brain_output({**GOOD_OUTPUT, "confidence": 1.7})

    def test_garbage_rejected(self):
        with pytest.raises(Exception):
            parse_brain_output("not even json-shaped")

    def test_missing_fields_rejected(self):
        with pytest.raises(Exception):
            parse_brain_output({"action": "buy"})

    def test_llm_cannot_set_cycle_id(self):
        d1 = parse_brain_output({**GOOD_OUTPUT})
        d2 = parse_brain_output({**GOOD_OUTPUT})
        assert d1.cycle_id != d2.cycle_id  # uuid per call, never from model


class TestPrompt:
    def test_system_prompt_carries_rules(self):
        assert f"{config.MAX_DRAWDOWN_PCT:.0f}%" in SYSTEM_PROMPT
        assert "mean_reversion" in SYSTEM_PROMPT  # explicitly disabled
        assert "NOT eligible" in SYSTEM_PROMPT    # BNB/WBNB warning

    def test_user_message_contains_signals_and_universe(self):
        snap = fetch_snapshot_from_fixtures()
        msg = build_user_message(snap, flat_portfolio())
        assert '"fear_greed"' in msg
        assert '"trending_narratives"' in msg
        assert '"eligible_tokens"' in msg
        assert "CAKE" in msg

    def test_history_included(self):
        snap = fetch_snapshot_from_fixtures()
        history = [{"action": "hold", "reasoning": "prior cycle"}]
        msg = build_user_message(snap, flat_portfolio(), history)
        assert "prior cycle" in msg


class TestMockBrainRouting:
    async def test_extreme_fear_routes_to_preservation(self):
        snap = fetch_snapshot_from_fixtures()  # real fixture: F&G = 15
        d = await decide(snap, flat_portfolio())
        assert d.regime == "high_risk"
        assert d.mode == "preservation"

    async def test_decision_validates_against_schema(self):
        snap = fetch_snapshot_from_fixtures()
        d = await decide(snap, flat_portfolio())
        assert 0.0 <= d.confidence <= 1.0
        assert d.reasoning
