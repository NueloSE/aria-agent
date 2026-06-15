"""Dashboard API — a read window onto the agent's SQLite plus the operator
controls (window, override, clear-halt). The dashboard NEVER trades; it only
reads state and writes the agent_state keys the loop already checks every cycle.

Run:  .venv/bin/uvicorn aria.api:app --port 8000 --reload
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aria import config, safety
from aria.safety import window
from aria.state.db import Store

app = FastAPI(title="ARIA dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # vite dev
    allow_methods=["*"],
    allow_headers=["*"],
)


def store() -> Store:
    # cheap per-request open; WAL allows concurrent agent writes
    return Store(config.DB_PATH)


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --- Read endpoints -------------------------------------------------------------

@app.get("/api/status")
def status() -> dict:
    s = store()
    last = _rows(s.conn,
                 "SELECT cycle_id, timestamp, regime, mode, action, token_symbol,"
                 " confidence, safety_verdict, outcome, reasoning"
                 " FROM decisions ORDER BY timestamp DESC LIMIT 1")
    snap = _rows(s.conn,
                 "SELECT timestamp, total_value_usd, peak_value_usd, drawdown_pct,"
                 " trades_today FROM portfolio_snapshots ORDER BY id DESC LIMIT 1")
    start, end = window.get_window(s)
    allowed, why = window.trading_allowed(s)
    return {
        "last_decision": last[0] if last else None,
        "portfolio": snap[0] if snap else None,
        "halted": safety.is_halted(s),
        "halt_reason": safety.halt_reason(s) or None,
        "trading_allowed": allowed,
        "trading_reason": why,
        "override": s.get_state(window.KEY_OVERRIDE),
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "config": {
            "network": config.NETWORK,
            "execution_mode": config.EXECUTION_MODE,
            "brain": f"{config.BRAIN_MODE}/{config.BRAIN_MODEL}",
            "halt_drawdown_pct": config.HALT_DRAWDOWN_PCT,
            "max_drawdown_pct": config.MAX_DRAWDOWN_PCT,
            "cycle_interval_min": config.CYCLE_INTERVAL_MIN,
            "wallet": config.AGENT_WALLET,
        },
        "trades_today": s.trades_today_utc(),
    }


@app.get("/api/decisions")
def decisions(limit: int = 50) -> list[dict]:
    rows = _rows(store().conn,
                 "SELECT cycle_id, timestamp, regime, mode, action, token_symbol,"
                 " size_pct, confidence, safety_verdict, outcome, reasoning"
                 " FROM decisions ORDER BY timestamp DESC LIMIT ?", (min(limit, 500),))
    return rows


@app.get("/api/decisions/{cycle_id}/signals")
def decision_signals(cycle_id: str) -> dict:
    rows = _rows(store().conn,
                 "SELECT signals_json FROM decisions WHERE cycle_id = ?", (cycle_id,))
    if not rows or not rows[0]["signals_json"]:
        raise HTTPException(404, "no signals recorded for this cycle")
    return json.loads(rows[0]["signals_json"])


@app.get("/api/portfolio")
def portfolio(limit: int = 1000) -> list[dict]:
    rows = _rows(store().conn,
                 "SELECT timestamp, total_value_usd, peak_value_usd, drawdown_pct,"
                 " trades_today FROM portfolio_snapshots ORDER BY id DESC LIMIT ?",
                 (min(limit, 5000),))
    return list(reversed(rows))  # chronological for charting


@app.get("/api/trades")
def trades(limit: int = 100) -> list[dict]:
    return _rows(store().conn,
                 "SELECT id, cycle_id, timestamp, kind, from_token, to_token,"
                 " from_amount, to_amount, tx_hash, status"
                 " FROM trades ORDER BY id DESC LIMIT ?", (min(limit, 500),))


# --- Operator controls ------------------------------------------------------------

class WindowBody(BaseModel):
    start: Optional[str] = None   # ISO-8601, UTC assumed if naive
    end: Optional[str] = None


@app.post("/api/window")
def set_window(body: WindowBody) -> dict:
    s = store()
    try:
        window.set_window(s, body.start, body.end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    start, end = window.get_window(s)
    return {"start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None}


class OverrideBody(BaseModel):
    value: Optional[str] = None   # "on" | "off" | null (clear)


@app.post("/api/override")
def set_override(body: OverrideBody) -> dict:
    s = store()
    try:
        window.set_override(s, body.value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    allowed, why = window.trading_allowed(s)
    return {"override": s.get_state(window.KEY_OVERRIDE),
            "trading_allowed": allowed, "trading_reason": why}


@app.post("/api/clear-halt")
def clear_halt() -> dict:
    s = store()
    if not safety.is_halted(s):
        return {"halted": False, "message": "agent was not halted"}
    safety.clear_halt(s)
    return {"halted": False, "message": "halt cleared — agent resumes next cycle"}
