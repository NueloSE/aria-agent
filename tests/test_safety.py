"""Safety layer tests — DESIGN.md hard rule #7: every circuit-breaker path
unit-tested before any real-money run. This file is the mainnet gate."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aria import config, safety
from aria.models import Decision, PortfolioState, Position
from aria.safety import compliance
from aria.state.db import Store

NOW = datetime.now(timezone.utc)


def portfolio(value: float = 100.0, peak: float = 100.0,
              positions: list[Position] | None = None) -> PortfolioState:
    return PortfolioState(timestamp=NOW, total_value_usd=value, peak_value_usd=peak,
                          stable_balance_usd=value, positions=positions or [])


def buy(token: str = "CAKE", size: float = 10.0, stop: float | None = 6.0,
        conf: float = 0.8, target: float | None = 10.0) -> Decision:
    return Decision(regime="trending", mode="narrative_rotation", action="buy",
                    token_symbol=token, size_pct=size, stop_loss_pct=stop,
                    target_pct=target, confidence=conf, reasoning="test")


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


class TestVetoPaths:
    def test_valid_buy_passes(self):
        safety.validate(buy(), portfolio())

    def test_low_confidence_vetoed(self):
        with pytest.raises(safety.Veto, match="confidence"):
            safety.validate(buy(conf=config.CONFIDENCE_FLOOR - 0.01), portfolio())

    def test_missing_token_vetoed(self):
        d = buy(); d.token_symbol = None
        with pytest.raises(safety.Veto, match="requires token_symbol"):
            safety.validate(d, portfolio())

    def test_ineligible_token_vetoed(self):
        with pytest.raises(safety.Veto, match="not in official"):
            safety.validate(buy(token="WBNB"), portfolio())

    def test_buy_without_stop_vetoed(self):
        with pytest.raises(safety.Veto, match="stop_loss"):
            safety.validate(buy(stop=None), portfolio())

    def test_zero_size_buy_vetoed(self):
        with pytest.raises(safety.Veto, match="size_pct"):
            safety.validate(buy(size=0.0), portfolio())

    def test_oversized_position_rejected_at_schema_level(self):
        with pytest.raises(Exception, match="MAX_POSITION_PCT"):
            buy(size=config.MAX_POSITION_PCT + 0.1)

    def test_hold_always_passes(self):
        d = Decision(regime="high_risk", mode="preservation", action="hold",
                     confidence=0.0, reasoning="x")
        safety.validate(d, portfolio(value=50, peak=100))  # even at 50% drawdown

    def test_close_all_always_passes_even_halted(self):
        d = Decision(regime="high_risk", mode="preservation", action="close_all",
                     confidence=1.0, reasoning="x")
        safety.validate(d, portfolio(value=50, peak=100), halted=True)


class TestDrawdownBreaker:
    def test_below_threshold_no_trigger(self):
        assert not safety.check_drawdown(portfolio(value=81, peak=100))  # 19%

    def test_at_threshold_triggers(self):
        assert safety.check_drawdown(portfolio(value=80, peak=100))      # exactly 20%

    def test_above_threshold_triggers(self):
        assert safety.check_drawdown(portfolio(value=70, peak=100))      # 30% = DQ

    def test_buy_vetoed_at_drawdown_even_unlatched(self):
        with pytest.raises(safety.Veto, match="drawdown"):
            safety.validate(buy(), portfolio(value=79, peak=100))

    def test_drawdown_computation_handles_zero_peak(self):
        assert portfolio(value=0, peak=0).drawdown_pct == 0.0


class TestHaltLatch:
    def test_latch_lifecycle(self, store):
        assert not safety.is_halted(store)
        safety.trigger_halt(store, "test breach")
        assert safety.is_halted(store)
        assert "test breach" in safety.halt_reason(store)
        safety.clear_halt(store)
        assert not safety.is_halted(store)

    def test_latch_survives_reopen(self, store, tmp_path):
        safety.trigger_halt(store, "crash test")
        reopened = Store(tmp_path / "test.sqlite3")   # simulates process restart
        assert safety.is_halted(reopened)

    def test_halted_blocks_buys(self, store):
        safety.trigger_halt(store, "x")
        with pytest.raises(safety.Veto, match="HALTED"):
            safety.validate(buy(), portfolio(), halted=True)

    def test_halted_allows_sell(self):
        d = Decision(regime="high_risk", mode="preservation", action="sell",
                     token_symbol="CAKE", confidence=0.9, reasoning="de-risk")
        safety.validate(d, portfolio(), halted=True)  # de-risking allowed


class TestComplianceScheduler:
    def _at(self, hour: int) -> datetime:
        return datetime(2026, 6, 23, hour, 0, tzinfo=timezone.utc)

    def test_not_due_early_in_day(self):
        assert not compliance.heartbeat_due(self._at(10), trades_today=0)

    def test_due_after_threshold_hour_with_no_trades(self):
        assert compliance.heartbeat_due(self._at(config.COMPLIANCE_TRADE_HOUR_UTC),
                                        trades_today=0)

    def test_not_due_when_already_traded(self):
        assert not compliance.heartbeat_due(self._at(23), trades_today=1)

    def test_due_at_end_of_day(self):
        assert compliance.heartbeat_due(self._at(23), trades_today=0)

    def test_pair_is_eligible_and_not_wbnb(self):
        frm, to = compliance.COMPLIANCE_PAIR
        assert frm in config.ELIGIBLE_SYMBOLS
        assert to in config.ELIGIBLE_SYMBOLS
        assert "WBNB" not in compliance.COMPLIANCE_PAIR

    def test_amount_floor_one_dollar(self):
        assert compliance.heartbeat_amount_usd(10.0) == 1.0      # 0.5% of $10 < $1
        assert compliance.heartbeat_amount_usd(1000.0) == 5.0    # 0.5% of $1000
