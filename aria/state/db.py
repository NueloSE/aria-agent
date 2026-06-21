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
-- Accumulated price series — CMC free tier sells no OHLCV history, so we BUILD
-- it: append each cycle's quotes. Over time this is a real price record.
CREATE TABLE IF NOT EXISTS price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    price_usd       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_symbol_ts ON price_history(symbol, id);
-- Paper-trading book: one row of cash + a positions table. Mirrors the on-chain
-- portfolio shape so the same safety/breaker logic runs on simulated PnL.
CREATE TABLE IF NOT EXISTS paper_book (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    stable_usd      REAL NOT NULL,
    peak_value_usd  REAL NOT NULL,
    started_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_positions (
    symbol          TEXT PRIMARY KEY,
    amount          REAL NOT NULL,
    entry_price_usd REAL NOT NULL,
    stop_loss_pct   REAL,
    target_pct      REAL,
    peak_gain_pct   REAL NOT NULL DEFAULT 0,
    opened_at       TEXT NOT NULL
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
        # WAL: the agent loop writes while the dashboard API reads concurrently
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
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
        # Capture starting capital on the very first snapshot — no manual config needed.
        if p.total_value_usd > 0 and not self.get_state("start_value_usd"):
            self.set_state("start_value_usd", str(p.total_value_usd))
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

    def set_cooldown(self, symbol: str, until_iso: str) -> None:
        # Never SHORTEN an existing cooldown (e.g. a 15-min reject cooldown must not
        # override a 120-min re-entry cooldown still in effect) — keep the later one.
        existing = self.get_state(f"cooldown:{symbol.upper()}")
        if existing:
            try:
                if datetime.fromisoformat(existing) > datetime.fromisoformat(until_iso):
                    return
            except ValueError:
                pass
        self.set_state(f"cooldown:{symbol.upper()}", until_iso)

    def in_cooldown(self, symbol: str) -> bool:
        v = self.get_state(f"cooldown:{symbol.upper()}")
        if not v:
            return False
        try:
            return datetime.fromisoformat(v) > datetime.now(timezone.utc)
        except ValueError:
            return False

    def cooled_down_tokens(self) -> set[str]:
        """Symbols whose cooldown (re-entry or judge-rejection) is still in effect —
        the gate excludes these so it surfaces the best NON-cooled candidate."""
        now = datetime.now(timezone.utc)
        rows = self.conn.execute(
            "SELECT key, value FROM agent_state WHERE key LIKE 'cooldown:%'"
        ).fetchall()
        out: set[str] = set()
        for key, value in rows:
            try:
                if datetime.fromisoformat(value) > now:
                    out.add(key.split(":", 1)[1])
            except (ValueError, IndexError):
                continue
        return out

    # --- Price accumulation -------------------------------------------------

    def record_prices(self, quotes: dict, ts: Optional[str] = None) -> None:
        """Append this cycle's token prices to the accumulated series."""
        from datetime import datetime, timezone
        ts = ts or datetime.now(timezone.utc).isoformat()
        rows = []
        for sym, q in quotes.items():
            price = q.get("price") if isinstance(q, dict) else None
            if isinstance(price, (int, float)) and price > 0:
                rows.append((ts, str(sym).upper(), float(price)))
        if rows:
            self.conn.executemany(
                "INSERT INTO price_history (timestamp, symbol, price_usd) VALUES (?,?,?)",
                rows,
            )
            self.conn.commit()

    def latest_prices(self) -> dict[str, float]:
        """Most recent price per symbol from the accumulated series."""
        rows = self.conn.execute(
            "SELECT symbol, price_usd FROM price_history"
            " WHERE id IN (SELECT MAX(id) FROM price_history GROUP BY symbol)"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # --- Paper book ---------------------------------------------------------

    def paper_book(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT stable_usd, peak_value_usd, started_at FROM paper_book WHERE id = 1"
        ).fetchone()
        if not row:
            return None
        return {"stable_usd": row[0], "peak_value_usd": row[1], "started_at": row[2]}

    def paper_book_init(self, stable_usd: float) -> None:
        from datetime import datetime, timezone
        self.conn.execute(
            "INSERT OR IGNORE INTO paper_book (id, stable_usd, peak_value_usd, started_at)"
            " VALUES (1, ?, ?, ?)",
            (stable_usd, stable_usd, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def paper_book_update(self, stable_usd: float, peak_value_usd: float) -> None:
        self.conn.execute(
            "UPDATE paper_book SET stable_usd = ?, peak_value_usd = ? WHERE id = 1",
            (stable_usd, peak_value_usd),
        )
        self.conn.commit()

    def paper_positions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT symbol, amount, entry_price_usd, stop_loss_pct, target_pct,"
            " peak_gain_pct, opened_at FROM paper_positions"
        ).fetchall()
        keys = ("symbol", "amount", "entry_price_usd", "stop_loss_pct", "target_pct",
                "peak_gain_pct", "opened_at")
        return [dict(zip(keys, r)) for r in rows]

    def paper_position_set(self, symbol: str, amount: float, entry_price_usd: float,
                           stop_loss_pct: Optional[float], opened_at: str,
                           target_pct: Optional[float] = None,
                           peak_gain_pct: float = 0.0) -> None:
        self.conn.execute(
            "INSERT INTO paper_positions (symbol, amount, entry_price_usd, stop_loss_pct,"
            " target_pct, peak_gain_pct, opened_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(symbol) DO UPDATE SET amount=excluded.amount,"
            " entry_price_usd=excluded.entry_price_usd, stop_loss_pct=excluded.stop_loss_pct,"
            " target_pct=excluded.target_pct, peak_gain_pct=excluded.peak_gain_pct",
            (symbol, amount, entry_price_usd, stop_loss_pct, target_pct, peak_gain_pct, opened_at),
        )
        self.conn.commit()

    def paper_position_peak(self, symbol: str, peak_gain_pct: float) -> None:
        self.conn.execute(
            "UPDATE paper_positions SET peak_gain_pct=? WHERE symbol=?",
            (peak_gain_pct, symbol),
        )
        self.conn.commit()

    def paper_position_delete(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol,))
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
