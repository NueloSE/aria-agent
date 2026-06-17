"""Fast-loop behavior: the LLM is event-driven (entry candidates only), posture
gates it out, cooldown blocks re-entry, and the adaptive holding flag is returned."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import aria.main as main_mod
from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.regime import RegimeCache, derive_posture
from aria.state.db import Store
from aria.strategies.base import Proposal, hold_proposal

NOW = datetime.now(timezone.utc)
QUOTES = {"LDO": {"symbol": "LDO", "price": 1.0, "percent_change_24h": 0.5,
                  "percent_change_7d": 6.0, "percent_change_30d": -22.0,
                  "volume_24h": 9_000_000.0}}


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "loop.sqlite3")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(config, "SIGNALS_MODE", "fixtures")
    monkeypatch.setattr(config, "BRAIN_MODE", "mock")
    monkeypatch.setattr(config, "EXECUTION_MODE", "stub")

    async def quotes():
        return QUOTES
    monkeypatch.setattr(main_mod.signals, "fetch_quotes_only", quotes)

    async def flat(*a, **k):
        return PortfolioState(timestamp=NOW, total_value_usd=100.0, peak_value_usd=100.0,
                              stable_balance_usd=100.0)
    monkeypatch.setattr(main_mod, "load_portfolio", flat)


def fresh_cache(fg: int) -> RegimeCache:
    s = MarketSnapshot(timestamp=NOW, fear_greed_index=fg, token_quotes=dict(QUOTES))
    c = RegimeCache()
    c.snapshot = s
    c.fetched_at = NOW                       # not stale -> no network refresh
    c.posture = derive_posture(s)
    return c


def candidate() -> Proposal:
    return Proposal(action="buy", token_symbol="LDO", size_pct=10.0,
                    stop_loss_pct=5.0, target_pct=7.0, rationale="oversold reclaim")


def last_decision(store: Store):
    return store.conn.execute(
        "SELECT action, safety_verdict FROM decisions ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()


class TestEventDrivenJudge:
    async def test_judge_not_called_when_posture_risk_off(self, store, monkeypatch):
        calls = []
        async def spy(*a, **k):
            calls.append(1)
            raise AssertionError("judge must not run under risk_off posture")
        monkeypatch.setattr(main_mod.brain, "judge_entry", spy)
        # gate WOULD find a candidate, but posture should short-circuit before the LLM
        async def scan(*a, **k):
            return candidate(), "mean_reversion"
        monkeypatch.setattr(main_mod.strategies, "scan_entries", scan)

        cache = fresh_cache(fg=10)           # extreme fear -> risk_off
        assert not cache.posture.allow_new_entries
        await main_mod.fast_tick(store, cache, dry_run=True)
        assert not calls
        assert last_decision(store)[0] == "hold"

    async def test_judge_called_and_approves_on_candidate(self, store, monkeypatch):
        calls = []
        async def scan(*a, **k):
            return candidate(), "mean_reversion"
        monkeypatch.setattr(main_mod.strategies, "scan_entries", scan)
        orig_judge = main_mod.brain.judge_entry
        async def spy(*a, **k):
            calls.append(1)
            return await orig_judge(*a, **k)
        monkeypatch.setattr(main_mod.brain, "judge_entry", spy)

        await main_mod.fast_tick(store, fresh_cache(fg=55), dry_run=True)
        assert calls == [1]                  # event-driven: exactly one entry judgment
        assert last_decision(store)[0] == "buy"

    async def test_no_candidate_means_no_judge_call(self, store, monkeypatch):
        calls = []
        async def scan(*a, **k):
            return hold_proposal("nothing washed out"), None
        monkeypatch.setattr(main_mod.strategies, "scan_entries", scan)
        async def spy(*a, **k):
            calls.append(1)
            raise AssertionError("judge must not run without a candidate")
        monkeypatch.setattr(main_mod.brain, "judge_entry", spy)

        await main_mod.fast_tick(store, fresh_cache(fg=55), dry_run=True)
        assert not calls
        assert last_decision(store)[0] == "hold"

    async def test_cooldown_blocks_entry_without_judge(self, store, monkeypatch):
        from datetime import timedelta
        store.set_cooldown("LDO", (NOW + timedelta(minutes=60)).isoformat())
        async def scan(*a, **k):
            return candidate(), "mean_reversion"
        monkeypatch.setattr(main_mod.strategies, "scan_entries", scan)
        calls = []
        async def spy(*a, **k):
            calls.append(1)
            raise AssertionError("judge must not run for a token in cooldown")
        monkeypatch.setattr(main_mod.brain, "judge_entry", spy)

        await main_mod.fast_tick(store, fresh_cache(fg=55), dry_run=True)
        assert not calls
        assert "cooldown" in store.conn.execute(
            "SELECT reasoning FROM decisions ORDER BY timestamp DESC LIMIT 1").fetchone()[0]


class TestAdaptiveCadence:
    async def test_flat_portfolio_reports_not_holding(self, store, monkeypatch):
        async def scan(*a, **k):
            return hold_proposal("no setup"), None
        monkeypatch.setattr(main_mod.strategies, "scan_entries", scan)
        _failures, holding = await main_mod.fast_tick(store, fresh_cache(fg=55), dry_run=True)
        assert holding is False
