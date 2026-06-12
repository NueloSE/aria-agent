"""Competition window + operator override tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aria import config
from aria.safety import window
from aria.state.db import Store

T0 = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)        # window start
T_END = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)     # window end


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "w.sqlite3")


def set_default_window(store):
    window.set_window(store, "2026-06-21T12:00:00Z", "2026-06-28T12:00:00Z")


class TestSchedule:
    def test_before_window_denied(self, store):
        set_default_window(store)
        allowed, why = window.trading_allowed(store, datetime(2026, 6, 20, tzinfo=timezone.utc))
        assert not allowed and "before window" in why

    def test_at_start_allowed(self, store):
        set_default_window(store)
        allowed, _ = window.trading_allowed(store, T0)
        assert allowed

    def test_inside_window_allowed(self, store):
        set_default_window(store)
        allowed, _ = window.trading_allowed(store, datetime(2026, 6, 24, tzinfo=timezone.utc))
        assert allowed

    def test_at_end_denied(self, store):
        set_default_window(store)
        allowed, why = window.trading_allowed(store, T_END)
        assert not allowed and "after window" in why

    def test_db_beats_env(self, store, monkeypatch):
        monkeypatch.setenv("COMPETITION_START_UTC", "2026-06-22T00:00:00Z")
        window.set_window(store, "2026-06-21T12:00:00Z", None)
        start, _ = window.get_window(store)
        assert start == T0  # the dashboard-set value, not env

    def test_env_seed_used_when_db_empty(self, store, monkeypatch):
        monkeypatch.setenv("COMPETITION_START_UTC", "2026-06-21T12:00:00Z")
        start, _ = window.get_window(store)
        assert start == T0

    def test_invalid_timestamp_rejected(self, store):
        with pytest.raises(ValueError):
            window.set_window(store, "next tuesday-ish", None)

    def test_naive_timestamp_treated_as_utc(self, store):
        window.set_window(store, "2026-06-21T12:00:00", None)
        start, _ = window.get_window(store)
        assert start == T0


class TestOverride:
    def test_emergency_stop_beats_open_window(self, store):
        set_default_window(store)
        window.set_override(store, "off")
        allowed, why = window.trading_allowed(store, datetime(2026, 6, 24, tzinfo=timezone.utc))
        assert not allowed and "EMERGENCY STOP" in why

    def test_override_on_beats_closed_window(self, store):
        set_default_window(store)
        window.set_override(store, "on")
        allowed, _ = window.trading_allowed(store, datetime(2026, 6, 1, tzinfo=timezone.utc))
        assert allowed

    def test_clearing_override_restores_schedule(self, store):
        set_default_window(store)
        window.set_override(store, "off")
        window.set_override(store, None)
        allowed, _ = window.trading_allowed(store, datetime(2026, 6, 24, tzinfo=timezone.utc))
        assert allowed

    def test_invalid_override_rejected(self, store):
        with pytest.raises(ValueError):
            window.set_override(store, "maybe")


class TestDefaults:
    def test_dev_mode_no_window_allowed(self, store):
        allowed, why = window.trading_allowed(store)
        assert allowed and "dev mode" in why

    def test_live_mode_no_window_DENIED(self, store, monkeypatch):
        """Real money + no window = operator error, not a default-open."""
        monkeypatch.setattr(config, "EXECUTION_MODE", "live")
        monkeypatch.setattr(config, "NETWORK", "mainnet")
        allowed, why = window.trading_allowed(store)
        assert not allowed and "no competition window" in why
