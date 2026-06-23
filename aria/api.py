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
        "regime": json.loads(s.get_state("regime")) if s.get_state("regime") else None,
        "config": {
            "network": config.NETWORK,
            "execution_mode": config.EXECUTION_MODE,
            "brain": f"{config.BRAIN_MODE}/{config.BRAIN_MODEL}",
            "halt_drawdown_pct": config.HALT_DRAWDOWN_PCT,
            "max_drawdown_pct": config.MAX_DRAWDOWN_PCT,
            "poll_interval_sec": config.POLL_INTERVAL_SEC,
            "poll_interval_flat_sec": config.POLL_INTERVAL_FLAT_SEC,
            "macro_refresh_sec": config.MACRO_REFRESH_SEC,
            "wallet": config.AGENT_WALLET,
            "readonly": config.DASHBOARD_READONLY,
        },
        "trades_today": s.trades_today_utc(),
        "cycles": s.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
    }


_STABLES = {"USDT", "USDC"}


def _live_positions(s: Store, prices: dict) -> list[dict]:
    """Live-mode open positions from the live_pos tracking (written on each confirmed
    swap). Paper mode uses paper_positions instead; live mode has no paper book."""
    out = []
    rows = s.conn.execute(
        "SELECT key, value FROM agent_state WHERE key LIKE 'live_pos:%'"
    ).fetchall()
    for key, val in rows:
        sym = key.split(":", 1)[1]
        try:
            pos = json.loads(val)
            amount = float(pos["amount"])
            entry = float(pos.get("entry_price") or 0.0)
        except (ValueError, TypeError, KeyError):
            continue
        if amount <= 0:
            continue
        px = prices.get(sym)
        value = (px * amount) if px else None
        gain = (px / entry - 1.0) * 100.0 if (px and entry) else None
        out.append({
            "symbol": sym, "amount": amount, "entry_price_usd": entry,
            "current_price_usd": px, "value_usd": value,
            "unrealized_pct": gain,
            "unrealized_usd": (value - entry * amount) if (value is not None) else None,
            "target_pct": pos.get("target_pct"), "stop_loss_pct": pos.get("stop_loss_pct"),
            "peak_gain_pct": None,
            "opened_at": pos.get("opened_at"),  # real ISO open time (was None -> 1970/"20627d ago")
        })
    return out


@app.get("/api/positions")
def positions() -> list[dict]:
    """Open positions marked to the latest accumulated prices, with unrealized PnL
    and progress toward the take-profit target / stop-loss."""
    s = store()
    prices = s.latest_prices()
    if config.EXECUTION_MODE == "live":
        return _live_positions(s, prices)
    out = []
    for p in s.paper_positions():
        sym = p["symbol"]
        px = prices.get(sym)
        entry = p["entry_price_usd"] or 0.0
        gain = (px / entry - 1.0) * 100.0 if (px and entry) else None
        value = (px * p["amount"]) if px else None
        out.append({
            "symbol": sym,
            "amount": p["amount"],
            "entry_price_usd": entry,
            "current_price_usd": px,
            "value_usd": value,
            "unrealized_pct": gain,
            "unrealized_usd": (value - entry * p["amount"]) if (value is not None) else None,
            "target_pct": p["target_pct"],
            "stop_loss_pct": p["stop_loss_pct"],
            "peak_gain_pct": p["peak_gain_pct"],
            "opened_at": p["opened_at"],
        })
    return out


@app.get("/api/performance")
def performance() -> dict:
    """Realized PnL by pairing strategy buy/sell legs into round-trips (FIFO per
    token), plus an unrealized roll-up from open positions. The trade-report the
    flat swap list never gave: did ARIA actually make money?"""
    from collections import defaultdict, deque

    s = store()
    legs = _rows(s.conn,
                 "SELECT timestamp, from_token, to_token, from_amount, to_amount, status"
                 " FROM trades WHERE kind='strategy' ORDER BY id")
    open_lots: dict[str, deque] = defaultdict(deque)
    round_trips: list[dict] = []
    for leg in legs:
        frm, to = leg["from_token"], leg["to_token"]
        try:
            from_amt = float(leg["from_amount"]) if leg["from_amount"] else 0.0
            to_amt = float(leg["to_amount"]) if leg["to_amount"] else 0.0
        except (TypeError, ValueError):
            continue
        if frm in _STABLES and to not in _STABLES:           # BUY: stables -> token
            open_lots[to].append((from_amt, leg["timestamp"]))
        elif to in _STABLES and frm not in _STABLES:         # SELL: token -> stables
            usd_in, opened = open_lots[frm].popleft() if open_lots[frm] else (0.0, None)
            pnl = to_amt - usd_in
            round_trips.append({
                "token": frm, "usd_in": usd_in, "usd_out": to_amt,
                "pnl_usd": pnl, "pnl_pct": (pnl / usd_in * 100.0) if usd_in else None,
                "opened_at": opened, "closed_at": leg["timestamp"],
            })

    realized = sum(rt["pnl_usd"] for rt in round_trips)
    wins = sum(1 for rt in round_trips if rt["pnl_usd"] > 0)
    losses = sum(1 for rt in round_trips if rt["pnl_usd"] < 0)
    unrealized = sum(p["unrealized_usd"] or 0.0 for p in positions())
    snap = _rows(s.conn, "SELECT total_value_usd, peak_value_usd FROM portfolio_snapshots"
                         " ORDER BY id DESC LIMIT 1")
    total_value = snap[0]["total_value_usd"] if snap else None
    recorded_start = s.get_state("start_value_usd")
    start = float(recorded_start) if recorded_start else config.PAPER_START_USD
    return {
        "total_value_usd": total_value,
        "start_value_usd": start,
        "total_return_pct": ((total_value - start) / start * 100.0) if total_value else None,
        "realized_pnl_usd": realized,
        "unrealized_pnl_usd": unrealized,
        "round_trips_total": len(round_trips),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": (wins / len(round_trips) * 100.0) if round_trips else None,
        "round_trips": list(reversed(round_trips)),  # newest first
    }


@app.get("/api/decisions")
def decisions(limit: int = 50, noteworthy: bool = False) -> list[dict]:
    # noteworthy = the decisions that actually did something: a trade (action != hold)
    # or a judge rejection / safety veto. Lets the dashboard surface real trades even
    # when they're thousands of quiet holds back in history.
    where = (
        " WHERE action != 'hold'"
        " OR safety_verdict LIKE 'vetoed%'"
        " OR reasoning LIKE '%judge rejected%'"
    ) if noteworthy else ""
    rows = _rows(store().conn,
                 "SELECT cycle_id, timestamp, regime, mode, action, token_symbol,"
                 " size_pct, confidence, safety_verdict, outcome, reasoning"
                 f" FROM decisions{where} ORDER BY timestamp DESC LIMIT ?", (min(limit, 500),))
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


def _bucket_ohlc(rows: list[dict], bucket_sec: int) -> list[dict]:
    """Aggregate a timestamped price series into OHLC candles. The series is the
    agent's accumulated CMC quotes (price_history) — CMC's free tier sells no OHLCV,
    so we build candles from the prices we've already paid a credit for each cycle."""
    from datetime import datetime

    buckets: dict[int, dict] = {}
    for r in rows:
        try:
            epoch = int(datetime.fromisoformat(r["timestamp"]).timestamp())
            px = float(r["price_usd"])
        except (TypeError, ValueError):
            continue
        b = epoch - (epoch % bucket_sec)
        c = buckets.get(b)
        if c is None:
            buckets[b] = {"time": b, "open": px, "high": px, "low": px, "close": px}
        else:
            c["high"] = max(c["high"], px)
            c["low"] = min(c["low"], px)
            c["close"] = px
    return [buckets[b] for b in sorted(buckets)]


@app.get("/api/candles")
def candles(symbol: Optional[str] = None, bucket: int = 900, limit: int = 240) -> dict:
    """OHLC candles per token, built from the accumulated CMC price series. Returns
    the list of symbols with enough history so the UI can offer a selector; with no
    symbol it picks the one with the most data."""
    bucket = max(60, min(bucket, 86_400))
    s = store()
    syms = _rows(s.conn,
                 "SELECT symbol, COUNT(*) AS n FROM price_history"
                 " GROUP BY symbol HAVING n >= 2 ORDER BY n DESC, symbol")
    available = [r["symbol"] for r in syms]
    if not available:
        return {"symbol": None, "bucket_sec": bucket, "symbols": [], "candles": []}
    sym = (symbol or available[0]).upper()
    if sym not in available:
        sym = available[0]
    rows = _rows(s.conn,
                 "SELECT timestamp, price_usd FROM price_history WHERE symbol = ? ORDER BY id",
                 (sym,))
    series = _bucket_ohlc(rows, bucket)
    return {"symbol": sym, "bucket_sec": bucket, "symbols": available,
            "candles": series[-min(limit, 1000):]}


# --- Operator controls ------------------------------------------------------------
# When DASHBOARD_READONLY is set (the public demo host), these endpoints are inert:
# the agent must never be steerable from an internet-facing URL.

def _guard_readonly() -> None:
    if config.DASHBOARD_READONLY:
        raise HTTPException(403, "dashboard is read-only — operator controls are disabled")


class WindowBody(BaseModel):
    start: Optional[str] = None   # ISO-8601, UTC assumed if naive
    end: Optional[str] = None


@app.post("/api/window")
def set_window(body: WindowBody) -> dict:
    _guard_readonly()
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
    _guard_readonly()
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
    _guard_readonly()
    s = store()
    if not safety.is_halted(s):
        return {"halted": False, "message": "agent was not halted"}
    safety.clear_halt(s)
    return {"halted": False, "message": "halt cleared — agent resumes next cycle"}


@app.post("/api/reset-peak")
def reset_peak() -> dict:
    """Reset peak_value_usd to current portfolio value so drawdown starts at 0%.
    Use after a halt caused by temporary losses you want to recover from."""
    _guard_readonly()
    s = store()
    snap = _rows(s.conn,
                 "SELECT total_value_usd FROM portfolio_snapshots ORDER BY id DESC LIMIT 1")
    if not snap:
        raise HTTPException(400, "no portfolio snapshot yet — agent hasn't run")
    current = snap[0]["total_value_usd"]
    s.set_state("peak_value_usd", str(current))
    safety.clear_halt(s)
    return {"peak_reset_to": current, "drawdown_pct": 0.0,
            "message": f"Peak reset to ${current:.2f}. Halt cleared. Agent resumes next cycle."}


# --- Serve the built dashboard from this same server (single URL, single process) ----
# `cd dashboard && npm run build` writes dashboard/dist; then this server hosts both the
# API and the UI on one port. Open http://localhost:8000/ — no separate dev server needed.
# (Registered LAST so it never shadows the /api/* routes above.)
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
if (_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(404, "Not Found")
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")  # SPA fallback (/, /dashboard, …)
