"""Paper-replay — a scripted week driven through the REAL paper engine.

Unlike replay_scenario.py (which scripts portfolio *values*), this feeds scripted
market *conditions* and lets the actual paper book compute PnL from real fills +
simulated costs. The mock brain reacts to each regime; the narrative gates pick
the token; the paper engine fills it and marks it to market.

Shows: trend entry → ride up → regime flip → lock profit → re-enter → drawdown →
cut loss. A realistic, honest curve (no manufactured moonshot), all free.

Run:
    .venv/bin/python scripts/paper_replay.py
View:
    ARIA_DB=paper_replay.sqlite3 .venv/bin/uvicorn aria.api:app --port 8000
    cd dashboard && npm run dev    -> http://localhost:5173/dashboard
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["ARIA_DB"] = str(ROOT / "paper_replay.sqlite3")
os.environ["EXECUTION_MODE"] = "paper"
os.environ["BRAIN_MODE"] = "mock"
os.environ["SIGNALS_MODE"] = "fixtures"  # unused (we inject snapshots) but set for safety

import aria.main as main_mod  # noqa: E402
from aria import config  # noqa: E402
from aria.models import MarketSnapshot  # noqa: E402
from aria.state.db import Store  # noqa: E402

GOOD_VOL = "120 M"

# (fg, label, narrative_7d, fet_price, note)
SCRIPT = [
    (68, "Greed",        "+9.4%",  1.40, "trend opens — enter FET"),
    (70, "Greed",        "+12.1%", 1.52, "riding the trend (+8.6%)"),
    (72, "Greed",        "+14.0%", 1.66, "trend strong (+18.6%)"),
    (69, "Greed",        "+7.2%",  1.78, "near the top (+27%)"),
    (46, "Neutral",      "+1.1%",  1.75, "regime flips ranging -> lock the gain"),
    (52, "Neutral",      "-0.4%",  1.70, "ranging, stand aside"),
    (41, "Neutral",      "-1.6%",  1.60, "still ranging, no edge"),
    (67, "Greed",        "+6.8%",  1.55, "trend returns -> re-enter FET"),
    (64, "Greed",        "+3.1%",  1.42, "position underwater (-8.4%)"),
    (61, "Greed",        "+1.0%",  1.30, "drawing down (-16%)"),
    (19, "Extreme fear", "-7.5%",  1.28, "fear hits -> cut the loss, go to stables"),
    (16, "Extreme fear", "-9.8%",  1.30, "risk-off, holding USDT"),
]


def snapshot(fg, label, n7d, fet, ts):
    return MarketSnapshot(
        timestamp=ts, fear_greed_index=fg, fear_greed_label=label,
        total_mcap_change_24h_pct=1.5 if fg >= 60 else -2.0,
        total_mcap_change_7d_pct=6.0 if fg >= 60 else -8.0,
        narratives=[{
            "trendingRank": 1, "categoryName": "AI Agents",
            "marketCapChangePercentage7d": n7d,
            "topCoinList": {"headers": ["coinSymbol"], "rows": [["FET"], ["INJ"], ["CAKE"]]},
        }],
        token_quotes={
            "FET": {"symbol": "FET", "price": fet, "volume_24h": GOOD_VOL},
            "ETH": {"symbol": "ETH", "price": 1800.0, "volume_24h": GOOD_VOL},
            "USDT": {"symbol": "USDT", "price": 1.0, "volume_24h": GOOD_VOL},
        },
        raw={"source": "paper-replay"},
    )


def respread_timestamps(store: Store, start: datetime, step: timedelta) -> None:
    """Cycles run in ~seconds; spread them across the week so the chart reads well.
    Map decisions + portfolio_snapshots by insertion order, then align trades."""
    dec_ids = [r[0] for r in store.conn.execute("SELECT cycle_id FROM decisions ORDER BY rowid")]
    snap_ids = [r[0] for r in store.conn.execute("SELECT id FROM portfolio_snapshots ORDER BY id")]
    for i, cid in enumerate(dec_ids):
        ts = (start + step * i).isoformat()
        store.conn.execute("UPDATE decisions SET timestamp=? WHERE cycle_id=?", (ts, cid))
        store.conn.execute("UPDATE trades SET timestamp=? WHERE cycle_id=?", (ts, cid))
    for i, sid in enumerate(snap_ids):
        ts = (start + step * i).isoformat()
        store.conn.execute("UPDATE portfolio_snapshots SET timestamp=? WHERE id=?", (ts, sid))
    store.conn.commit()


async def run() -> None:
    db = Path(os.environ["ARIA_DB"])
    if db.exists():
        db.unlink()
    store = Store(db)
    start = datetime.now(timezone.utc) - timedelta(days=6)
    step = timedelta(hours=12)

    for i, (fg, label, n7d, fet, note) in enumerate(SCRIPT):
        snap = snapshot(fg, label, n7d, fet, start + step * i)

        async def fake_fetch():
            return snap

        async def fake_quotes():
            return snap.token_quotes

        # The two-speed loop reads quotes (fast) and macro (cached) separately —
        # inject the scripted step into BOTH so the regime + entry gates see it.
        main_mod.signals.fetch_snapshot = fake_fetch        # type: ignore[assignment]
        main_mod.signals.fetch_quotes_only = fake_quotes    # type: ignore[assignment]
        await main_mod.run_cycle(store, dry_run=False)

        book = store.paper_book()
        positions = store.paper_positions()
        pos = f"holding {positions[0]['symbol']} {positions[0]['amount']:.2f}" if positions else "in stables"
        # mark current total
        from aria.execution import paper
        total = paper.load_state(store).total_value_usd
        print(f"[{i:02d}] F&G {fg:2d} FET ${fet:.2f} | ${total:6.2f} | {pos:18s} | {note}")

    respread_timestamps(store, start, step)

    # summary
    final = store.conn.execute(
        "SELECT total_value_usd FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    trades = store.conn.execute(
        "SELECT from_token, to_token, from_amount, to_amount FROM trades"
        " WHERE kind='strategy' ORDER BY id").fetchall()
    print(f"\n--- paper week complete ---")
    print(f"start ${config.PAPER_START_USD:.2f}  ->  end ${final:.2f}  "
          f"({(final/config.PAPER_START_USD - 1) * 100:+.2f}%)")
    print(f"strategy trades: {len(trades)} (cost model: {config.SIM_COST_PCT_PER_LEG}%/leg)")
    for t in trades:
        print(f"   {t[0]} -> {t[1]}   in={t[2]}  out={t[3]}")
    print(f"\nview it:\n  ARIA_DB=paper_replay.sqlite3 .venv/bin/uvicorn aria.api:app --port 8000")


if __name__ == "__main__":
    asyncio.run(run())
