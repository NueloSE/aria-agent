"""Circuit-breaker INTEGRATION test — the Stage 6 exit criterion.

Simulates the judged week's nightmare: portfolio slides toward the 30% DQ gate.
Asserts the full chain: breach -> close_all -> persistent halt -> buys refused ->
compliance heartbeat still fires while halted -> manual --clear-halt resumes.
Runs the REAL run_cycle loop with monkeypatched portfolio values (fixtures signals).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import aria.main as main_mod
from aria import config, safety
from aria.models import PortfolioState
from aria.state.db import Store


def make_portfolio(value: float, peak: float = 100.0) -> PortfolioState:
    return PortfolioState(timestamp=datetime.now(timezone.utc), total_value_usd=value,
                          peak_value_usd=peak, stable_balance_usd=value)


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "cb.sqlite3")


@pytest.fixture(autouse=True)
def fixtures_mode(monkeypatch):
    monkeypatch.setattr(config, "SIGNALS_MODE", "fixtures")
    monkeypatch.setattr(config, "BRAIN_MODE", "mock")


async def run_with_value(store: Store, monkeypatch, value: float) -> None:
    async def fake_load(*args, **kwargs) -> PortfolioState:
        return make_portfolio(value)

    monkeypatch.setattr(main_mod, "load_portfolio", fake_load)
    await main_mod.run_cycle(store, dry_run=True)


class TestPnLSlide:
    async def test_full_breach_sequence(self, store, monkeypatch):
        # Healthy cycles: 100 -> 95 -> 85 (15% dd) — no halt
        for value in (100.0, 95.0, 85.0):
            await run_with_value(store, monkeypatch, value)
            assert not safety.is_halted(store), f"halted too early at {value}"

        # 79 = 21% drawdown -> breach: close_all + latch
        await run_with_value(store, monkeypatch, 79.0)
        assert safety.is_halted(store)
        row = store.conn.execute(
            "SELECT action, safety_verdict FROM decisions ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "close_all"
        assert row[1] == "halt_triggered"

        # Next cycle (even if value recovers): still halted, only holds
        await run_with_value(store, monkeypatch, 90.0)
        assert safety.is_halted(store)
        row = store.conn.execute(
            "SELECT action, safety_verdict FROM decisions ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "hold"
        assert row[1] == "halted"

        # Manual restart releases the latch; trading resumes
        safety.clear_halt(store)
        await run_with_value(store, monkeypatch, 90.0)
        assert not safety.is_halted(store)
        row = store.conn.execute(
            "SELECT safety_verdict FROM decisions ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        assert row[0] not in ("halted", "halt_triggered")

    async def test_heartbeat_fires_while_halted(self, store, monkeypatch):
        """Going silent for a day violates the rules — even a halted agent must
        make its daily compliance trade."""
        safety.trigger_halt(store, "pre-halted")
        # Force "heartbeat due": late in the UTC day, zero trades
        monkeypatch.setattr(
            main_mod.compliance, "heartbeat_due",
            lambda now_utc=None, trades_today=0: True,
        )
        await run_with_value(store, monkeypatch, 75.0)
        trade = store.conn.execute(
            "SELECT kind, from_token, to_token FROM trades ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert trade == ("compliance", "USDT", "ETH")

    async def test_breach_cycle_skips_brain_entirely(self, store, monkeypatch):
        """At breach, the LLM is not consulted — the rule engine acts alone. The brain
        is now only the entry JUDGE, so that is what must never fire during a breach."""
        called = []

        async def spy_judge(*a, **k):  # pragma: no cover - should never run
            called.append(1)
            raise AssertionError("brain must not be consulted during breach")

        monkeypatch.setattr(main_mod.brain, "judge_entry", spy_judge)
        await run_with_value(store, monkeypatch, 70.0)  # 30% dd
        assert safety.is_halted(store)
        assert not called
