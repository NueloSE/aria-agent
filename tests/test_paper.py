"""Paper-trading engine tests — deterministic fill math, mark-to-market, and the
full pipeline running on simulated PnL (including the breaker tripping on it)."""
from __future__ import annotations

import pytest

import aria.main as main_mod
from aria import config
from aria.execution import paper
from aria.models import Decision, MarketSnapshot
from aria.state.db import Store


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXECUTION_MODE", "paper")
    monkeypatch.setattr(config, "PAPER_START_USD", 100.0)
    monkeypatch.setattr(config, "SIM_COST_PCT_PER_LEG", 0.75)
    s = Store(tmp_path / "paper.sqlite3")
    paper.ensure_init(s)
    return s


def buy(token="CAKE", size=10.0, stop=6.0) -> Decision:
    return Decision(regime="trending", mode="narrative_rotation", action="buy",
                    token_symbol=token, size_pct=size, stop_loss_pct=stop,
                    confidence=0.8, reasoning="t")


def close() -> Decision:
    return Decision(regime="high_risk", mode="preservation", action="close_all",
                    confidence=1.0, reasoning="t")


def seed_position(store: Store, symbol: str, amount: float, entry: float,
                  stable_left: float) -> None:
    """Place a position + cash directly — simulates a book accumulated over many
    cycles (each buy is <=15%, but the book can be mostly deployed in aggregate)."""
    from datetime import datetime, timezone
    store.paper_position_set(symbol, amount, entry, 6.0, datetime.now(timezone.utc).isoformat())
    store.paper_book_update(stable_left, store.paper_book()["peak_value_usd"])


class TestFillMath:
    def test_buy_applies_cost_and_records_position(self, store):
        store.record_prices({"CAKE": {"price": 2.0}})
        r = paper.simulate(store, buy(size=10.0), total_value_usd=100.0)
        assert r.status == "executed"
        # spend $10, cost 0.75% = $0.075, net $9.925 / $2 = 4.9625 CAKE
        pos = store.paper_positions()[0]
        assert pos["symbol"] == "CAKE"
        assert pos["amount"] == pytest.approx(9.925 / 2.0)
        assert store.paper_book()["stable_usd"] == pytest.approx(90.0)

    def test_buy_without_price_skips(self, store):
        r = paper.simulate(store, buy(token="FET"), total_value_usd=100.0)
        assert r.status == "skipped"
        assert store.paper_positions() == []

    def test_close_returns_proceeds_minus_cost(self, store):
        # bought 25 CAKE @ $2 ($50), $50 cash left
        seed_position(store, "CAKE", 25.0, 2.0, stable_left=50.0)
        store.record_prices({"CAKE": {"price": 4.0}})  # price doubled
        r = paper.simulate(store, close(), total_value_usd=999.0)
        assert r.status == "executed"
        assert store.paper_positions() == []
        # 25 @ $4 = $100 gross, minus 0.75% = $99.25, + $50 cash = ~$149.25
        assert store.paper_book()["stable_usd"] == pytest.approx(50 + 100 * 0.9925)

    def test_buy_capped_at_stable_balance(self, store):
        store.record_prices({"CAKE": {"price": 1.0}})
        # size 15% of a claimed $10000 total, but only $100 stable exists
        d = buy(size=15.0)
        paper.simulate(store, d, total_value_usd=10000.0)
        assert store.paper_book()["stable_usd"] >= 0  # never goes negative


class TestMarkToMarket:
    def test_flat_start(self, store):
        p = paper.load_state(store)
        assert p.total_value_usd == pytest.approx(100.0)
        assert p.drawdown_pct == 0.0

    def test_position_valued_at_live_price(self, store):
        seed_position(store, "CAKE", 25.0, 2.0, stable_left=50.0)  # $50 cash + 25 CAKE
        store.record_prices({"CAKE": {"price": 3.0}})  # +50% from entry
        p = paper.load_state(store)
        assert p.total_value_usd == pytest.approx(50 + 25 * 3.0)  # $125
        assert len(p.positions) == 1

    def test_drawdown_tracks_peak(self, store):
        seed_position(store, "CAKE", 10.0, 10.0, stable_left=0.0)  # fully deployed, $100
        store.record_prices({"CAKE": {"price": 10.0}})
        paper.load_state(store)  # sets peak ~100
        store.record_prices({"CAKE": {"price": 7.0}})  # -30% on the position
        p = paper.load_state(store)
        assert p.drawdown_pct > 20  # deep enough to trip the breaker


class TestComplianceRoundtrip:
    def test_costs_two_legs_no_position(self, store):
        store.record_prices({"ETH": {"price": 1600.0}})
        r = paper.compliance_roundtrip(store, "c1", amount_usd=5.0)
        assert r.status == "executed"
        assert store.paper_positions() == []  # round trip leaves no position
        assert store.paper_book()["stable_usd"] < 100  # lost the two-leg cost


class TestFullPipelinePaper:
    async def test_breaker_trips_on_paper_drawdown(self, store, tmp_path, monkeypatch):
        """Buy, then the price craters -> paper drawdown >= 20% -> circuit breaker
        fires through the REAL run_cycle, on simulated PnL."""
        monkeypatch.setattr(config, "SIGNALS_MODE", "fixtures")
        monkeypatch.setattr(config, "BRAIN_MODE", "mock")

        # seed: a fully-deployed book bought high (accumulated over prior cycles)
        seed_position(store, "CAKE", 10.0, 10.0, stable_left=0.0)
        store.record_prices({"CAKE": {"price": 10.0}})
        paper.load_state(store)  # peak ~100

        # now feed a crashed snapshot through the real loop
        crashed = MarketSnapshot(
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            fear_greed_index=12, fear_greed_label="Extreme fear",
            token_quotes={"CAKE": {"symbol": "CAKE", "price": 6.5}},  # -35%
        )

        async def fake_fetch():
            return crashed

        monkeypatch.setattr(main_mod.signals, "fetch_snapshot", fake_fetch)
        from aria import safety
        assert not safety.is_halted(store)
        # Debounced breaker: the breach must persist DRAWDOWN_BREACH_CONFIRM cycles.
        for _ in range(config.DRAWDOWN_BREACH_CONFIRM):
            await main_mod.run_cycle(store, dry_run=False)
        assert safety.is_halted(store)  # breaker fired on paper PnL
