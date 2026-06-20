"""Fee-aware min-edge gate, stepped trailing stop, and the position manager."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aria import config, safety
from aria.execution.manager import _exit_reason
from aria.models import Decision, PortfolioState, Position

NOW = datetime.now(timezone.utc)


def buy(target: float | None) -> Decision:
    return Decision(regime="trending", mode="narrative_rotation", action="buy",
                    token_symbol="CAKE", size_pct=10.0, stop_loss_pct=6.0,
                    target_pct=target, confidence=0.8, reasoning="t")


def flat() -> PortfolioState:
    return PortfolioState(timestamp=NOW, total_value_usd=100.0, peak_value_usd=100.0,
                          stable_balance_usd=100.0)


class TestFeeGate:
    def test_no_target_vetoed(self):
        with pytest.raises(safety.Veto, match="fee-gate"):
            safety.validate(buy(None), flat())

    def test_target_below_minimum_vetoed(self):
        # min = MIN_EDGE_MULTIPLE x round-trip cost; use a target just under it
        below = config.round_trip_cost_pct() * config.MIN_EDGE_MULTIPLE / 2
        with pytest.raises(safety.Veto, match="fee-gate"):
            safety.validate(buy(below), flat())

    def test_adequate_target_passes(self):
        safety.validate(buy(10.0), flat())

    def test_boundary_target_passes(self):
        mn = config.round_trip_cost_pct() * config.MIN_EDGE_MULTIPLE
        safety.validate(buy(mn), flat())


class TestTrailingStop:
    def test_unarmed_below_trigger(self):
        assert safety.trailing_stop_for(config.TRAIL_TRIGGER_PCT - 0.1) is None

    def test_arms_at_trigger(self):
        assert safety.trailing_stop_for(config.TRAIL_TRIGGER_PCT) == config.TRAIL_INITIAL_SL_PCT

    def test_trails_up_with_peak(self):
        # one full step past the trigger -> stop rises by one step
        s = safety.trailing_stop_for(config.TRAIL_TRIGGER_PCT + config.TRAIL_STEP_PCT)
        assert s == pytest.approx(config.TRAIL_INITIAL_SL_PCT + config.TRAIL_STEP_PCT)

    def test_locks_profit(self):
        # once armed, the stop is always a POSITIVE gain — can't close red
        assert safety.trailing_stop_for(5.0) > 0


class TestExitReason:
    def test_take_profit_first(self):
        assert _exit_reason(gain=8.0, peak=8.0, target=7.0, stop_loss=5.0) == "take_profit"

    def test_trailing_stop(self):
        # peaked at +4% (armed), now back to +0.5% which is below the trailing stop
        peak = 4.0
        assert safety.trailing_stop_for(peak) is not None
        assert _exit_reason(gain=0.5, peak=peak, target=7.0, stop_loss=5.0) == "trailing_stop"

    def test_hard_stop(self):
        assert _exit_reason(gain=-6.0, peak=0.0, target=7.0, stop_loss=5.0) == "stop_loss"

    def test_no_exit_while_running(self):
        # up +1.5%, never armed the trail (trigger is 2.5%), above hard stop
        assert _exit_reason(gain=1.5, peak=1.5, target=7.0, stop_loss=5.0) is None


class TestManagerExecutesExits:
    async def test_take_profit_sells_paper_position(self, tmp_path, monkeypatch):
        from aria.execution import paper
        from aria.execution.manager import manage_open_positions
        from aria.state.db import Store

        monkeypatch.setattr(config, "EXECUTION_MODE", "paper")
        store = Store(tmp_path / "m.sqlite3")
        paper.ensure_init(store)
        # seed a CAKE position entered at $2 with a +7% target
        store.paper_position_set("CAKE", 25.0, 2.0, 5.0,
                                 NOW.isoformat(), target_pct=7.0, peak_gain_pct=0.0)
        store.paper_book_update(50.0, 100.0)
        portfolio = paper.load_state(store)
        # price now $2.20 (+10%) -> take profit fires
        notes = await manage_open_positions(portfolio, {"CAKE": 2.20}, store, dry_run=False)
        assert any("take_profit" in n for n in notes)
        assert store.paper_positions() == []  # sold
