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

    def test_signals_404_when_absent(self, client):
        cid = client.get("/api/decisions").json()[0]["cycle_id"]
        assert client.get(f"/api/decisions/{cid}/signals").status_code == 404

    def test_portfolio_empty_ok(self, client):
        assert client.get("/api/portfolio").json() == []


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
