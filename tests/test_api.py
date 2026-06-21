"""Dashboard API tests — TestClient against a temp DB, no live anything."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aria import config, safety
from aria.api import app
from aria.models import hold_decision
from aria.state.db import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", db)
    s = Store(db)
    s.log_decision(hold_decision("seed decision"), safety_verdict="dry_run")
    return TestClient(app)


class TestReads:
    def test_status_shape(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        body = r.json()
        assert body["last_decision"]["action"] == "hold"
        assert body["halted"] is False
        assert "window" in body and "config" in body

    def test_decisions_list(self, client):
        rows = client.get("/api/decisions").json()
        assert len(rows) == 1
        assert rows[0]["reasoning"] == "seed decision"

    def test_decisions_noteworthy_filter(self, client):
        from aria.models import Decision
        s = Store(config.DB_PATH)
        # a real trade decision + a judge rejection, amid the seeded hold
        s.log_decision(
            Decision(regime="trending", mode="narrative_rotation", action="buy",
                     token_symbol="CAKE", size_pct=10.0, stop_loss_pct=5.0,
                     confidence=0.8, reasoning="strategy: breakout | judge: approved"),
            safety_verdict="approved")
        s.log_decision(
            Decision(regime="ranging", mode="mean_reversion", action="hold",
                     token_symbol=None, size_pct=0.0, confidence=0.4,
                     reasoning="strategy: mr | judge rejected: low conviction"),
            safety_verdict="vetoed_confidence")
        all_rows = client.get("/api/decisions").json()
        assert len(all_rows) == 3
        note = client.get("/api/decisions?noteworthy=1").json()
        actions = [r["action"] for r in note]
        assert "buy" in actions          # the trade is surfaced
        assert "hold" in actions         # the rejection (a hold) is surfaced too
        assert len(note) == 2            # the plain seed hold is excluded

    def test_positions_empty_ok(self, client):
        assert client.get("/api/positions").json() == []

    def test_positions_marked_with_pnl(self, client):
        from datetime import datetime, timezone
        s = Store(config.DB_PATH)
        now = datetime.now(timezone.utc).isoformat()
        s.paper_position_set("CAKE", 10.0, 2.0, 5.0, now, target_pct=7.0, peak_gain_pct=1.0)
        s.record_prices({"CAKE": {"price": 2.2}})  # +10%
        pos = client.get("/api/positions").json()
        assert len(pos) == 1
        assert pos[0]["symbol"] == "CAKE"
        assert pos[0]["unrealized_pct"] == pytest.approx(10.0)
        assert pos[0]["value_usd"] == pytest.approx(22.0)

    def test_performance_realized_roundtrip(self, client):
        s = Store(config.DB_PATH)
        # a winning round-trip: $10 in -> $11 out, and a losing one: $10 -> $9.50
        s.log_trade("c1", "strategy", "USDT", "CAKE", "confirmed", from_amount="10", to_amount="5")
        s.log_trade("c2", "strategy", "CAKE", "USDT", "confirmed", from_amount="5", to_amount="11")
        s.log_trade("c3", "strategy", "USDT", "UNI", "confirmed", from_amount="10", to_amount="2")
        s.log_trade("c4", "strategy", "UNI", "USDT", "confirmed", from_amount="2", to_amount="9.5")
        perf = client.get("/api/performance").json()
        assert perf["round_trips_total"] == 2
        assert perf["wins"] == 1 and perf["losses"] == 1
        assert perf["realized_pnl_usd"] == pytest.approx(0.5)  # +1.0 and -0.5
        assert perf["win_rate_pct"] == pytest.approx(50.0)

    def test_signals_404_when_absent(self, client):
        cid = client.get("/api/decisions").json()[0]["cycle_id"]
        assert client.get(f"/api/decisions/{cid}/signals").status_code == 404

    def test_portfolio_empty_ok(self, client):
        assert client.get("/api/portfolio").json() == []

    def test_status_reports_cycles(self, client):
        # the fixture seeds one decision
        assert client.get("/api/status").json()["cycles"] == 1

    def test_candles_empty_ok(self, client):
        body = client.get("/api/candles").json()
        assert body == {"symbol": None, "bucket_sec": 900, "symbols": [], "candles": []}

    def test_candles_ohlc_aggregation(self, client):
        from datetime import datetime, timezone
        s = Store(config.DB_PATH)
        base = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
        # four ticks inside one 15-min bucket: prices 10, 12, 9, 11
        for i, px in enumerate((10.0, 12.0, 9.0, 11.0)):
            ts = base.replace(minute=i).isoformat()
            s.record_prices({"ETH": {"price": px}}, ts=ts)
        body = client.get("/api/candles?symbol=ETH&bucket=900").json()
        assert body["symbol"] == "ETH"
        assert body["symbols"] == ["ETH"]
        assert len(body["candles"]) == 1
        c = body["candles"][0]
        assert (c["open"], c["high"], c["low"], c["close"]) == (10.0, 12.0, 9.0, 11.0)


class TestControls:
    def test_set_window_roundtrip(self, client):
        r = client.post("/api/window", json={"start": "2026-06-21T12:00:00Z",
                                             "end": "2026-06-28T12:00:00Z"})
        assert r.status_code == 200
        assert r.json()["start"] == "2026-06-21T12:00:00+00:00"
        status = client.get("/api/status").json()
        assert status["window"]["start"] is not None

    def test_invalid_window_422(self, client):
        assert client.post("/api/window", json={"start": "soonish"}).status_code == 422

    def test_emergency_stop_and_resume(self, client):
        r = client.post("/api/override", json={"value": "off"})
        assert r.json()["trading_allowed"] is False
        r = client.post("/api/override", json={"value": None})
        assert r.json()["override"] is None

    def test_invalid_override_422(self, client):
        assert client.post("/api/override", json={"value": "maybe"}).status_code == 422

    def test_clear_halt(self, client, tmp_path):
        s = Store(config.DB_PATH)
        safety.trigger_halt(s, "test")
        assert client.get("/api/status").json()["halted"] is True
        r = client.post("/api/clear-halt")
        assert r.json()["halted"] is False
        assert client.get("/api/status").json()["halted"] is False


class TestReadonly:
    """With DASHBOARD_READONLY set (the public demo host) the control POSTs are
    inert (403) while every read endpoint still works."""

    @pytest.fixture()
    def ro_client(self, client, monkeypatch):
        monkeypatch.setattr(config, "DASHBOARD_READONLY", True)
        return client

    def test_status_exposes_readonly_flag(self, ro_client):
        assert ro_client.get("/api/status").json()["config"]["readonly"] is True

    def test_reads_still_work(self, ro_client):
        assert ro_client.get("/api/positions").status_code == 200
        assert ro_client.get("/api/decisions").status_code == 200

    def test_window_blocked(self, ro_client):
        assert ro_client.post("/api/window", json={"start": "2026-06-21T12:00:00Z"}).status_code == 403

    def test_override_blocked(self, ro_client):
        assert ro_client.post("/api/override", json={"value": "off"}).status_code == 403

    def test_clear_halt_blocked(self, ro_client):
        assert ro_client.post("/api/clear-halt").status_code == 403

    def test_default_is_writable(self, client):
        assert client.get("/api/status").json()["config"]["readonly"] is False
        assert client.post("/api/override", json={"value": None}).status_code == 200
