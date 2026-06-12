"""SQLite persistence: decision audit trail, trades, portfolio snapshots.
Every cycle writes a decision row — including holds. Sync sqlite3 is fine here
(one writer, low frequency)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aria.models import Decision, PortfolioState

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    cycle_id        TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    regime          TEXT NOT NULL,
    mode            TEXT NOT NULL,
    action          TEXT NOT NULL,
    token_symbol    TEXT,
    size_pct        REAL NOT NULL,
    stop_loss_pct   REAL,
    confidence      REAL NOT NULL,
    reasoning       TEXT NOT NULL,
    signals_json    TEXT,            -- MarketSnapshot dump for the audit trail
    safety_verdict  TEXT,            -- approved | vetoed:<reason> | dry_run
    outcome         TEXT             -- filled after execution (tx hash / error / skipped)
);
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id        TEXT REFERENCES decisions(cycle_id),
    timestamp       TEXT NOT NULL,
    kind            TEXT NOT NULL,   -- strategy | compliance
    from_token      TEXT NOT NULL,
    to_token        TEXT NOT NULL,
    from_amount     TEXT,
    to_amount       TEXT,
    tx_hash         TEXT,
    status          TEXT NOT NULL    -- quoted | submitted | confirmed | failed
);
CREATE TABLE IF NOT EXISTS agent_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    total_value_usd REAL NOT NULL,
    peak_value_usd  REAL NOT NULL,
    drawdown_pct    REAL NOT NULL,
    positions_json  TEXT NOT NULL,
    trades_today    INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def log_decision(
        self,
        decision: Decision,
        signals_json: Optional[str] = None,
        safety_verdict: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO decisions (cycle_id, timestamp, regime, mode, action,"
            " token_symbol, size_pct, stop_loss_pct, confidence, reasoning,"
            " signals_json, safety_verdict)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision.cycle_id,
                decision.timestamp.isoformat(),
                decision.regime,
                decision.mode,
                decision.action,
                decision.token_symbol,
                decision.size_pct,
                decision.stop_loss_pct,
                decision.confidence,
                decision.reasoning,
                signals_json,
                safety_verdict,
            ),
        )
        self.conn.commit()

    def set_outcome(self, cycle_id: str, outcome: str) -> None:
        self.conn.execute(
            "UPDATE decisions SET outcome = ? WHERE cycle_id = ?", (outcome, cycle_id)
        )
        self.conn.commit()

    def log_trade(self, cycle_id: str, kind: str, from_token: str, to_token: str,
                  status: str, **fields: str) -> None:
        self.conn.execute(
            "INSERT INTO trades (cycle_id, timestamp, kind, from_token, to_token,"
            " from_amount, to_amount, tx_hash, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                cycle_id,
                datetime.now(timezone.utc).isoformat(),
                kind,
                from_token,
                to_token,
                fields.get("from_amount"),
                fields.get("to_amount"),
                fields.get("tx_hash"),
                status,
            ),
        )
        self.conn.commit()

    def snapshot_portfolio(self, p: PortfolioState) -> None:
        self.conn.execute(
            "INSERT INTO portfolio_snapshots (timestamp, total_value_usd,"
            " peak_value_usd, drawdown_pct, positions_json, trades_today)"
            " VALUES (?,?,?,?,?,?)",
            (
                p.timestamp.isoformat(),
                p.total_value_usd,
                p.peak_value_usd,
                p.drawdown_pct,
                json.dumps([pos.model_dump(mode="json") for pos in p.positions]),
                p.trades_today,
            ),
        )
        self.conn.commit()

    # --- Agent state (halt latch etc.) ---------------------------------------

    def get_state(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM agent_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO agent_state (key, value, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            " updated_at=excluded.updated_at",
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def clear_state(self, key: str) -> None:
        self.conn.execute("DELETE FROM agent_state WHERE key = ?", (key,))
        self.conn.commit()

    def trades_today_utc(self, kinds: tuple[str, ...] = ("strategy", "compliance")) -> int:
        """Confirmed trades since UTC midnight (the competition's daily boundary)."""
        midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        placeholders = ",".join("?" for _ in kinds)
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM trades WHERE timestamp >= ?"
            f" AND status = 'confirmed' AND kind IN ({placeholders})",
            (midnight, *kinds),
        ).fetchone()
        return int(row[0])

    def recent_decisions(self, n: int = 5) -> list[dict]:
        """Compact history for the brain prompt — newest first."""
        rows = self.conn.execute(
            "SELECT timestamp, regime, mode, action, token_symbol, confidence,"
            " safety_verdict, outcome, reasoning FROM decisions"
            " ORDER BY timestamp DESC LIMIT ?",
            (n,),
        ).fetchall()
        keys = ("timestamp", "regime", "mode", "action", "token", "confidence",
                "verdict", "outcome", "reasoning")
        out = []
        for row in rows:
            d = dict(zip(keys, row))
            d["reasoning"] = (d["reasoning"] or "")[:200]  # keep prompt small
            out.append(d)
        return out

    def trades_since(self, iso_ts: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE timestamp >= ? AND status = 'confirmed'",
            (iso_ts,),
        ).fetchone()
        return int(row[0])
