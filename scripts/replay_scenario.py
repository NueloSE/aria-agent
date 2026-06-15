"""Replay scenario — drives the REAL agent loop through a scripted week so the
dashboard can show regime transitions and the circuit breaker firing, regardless
of what the live market does during judging.

Writes to its own database (replay.sqlite3). View it:
    ARIA_DB=replay.sqlite3 .venv/bin/uvicorn aria.api:app --port 8000
    open http://localhost:5173/dashboard

Run:
    SIGNALS_MODE=fixtures ARIA_DB=replay.sqlite3 .venv/bin/python scripts/replay_scenario.py

Everything is dry-run; execution is structurally impossible here.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ARIA_DB", str(ROOT / "replay.sqlite3"))
os.environ.setdefault("SIGNALS_MODE", "fixtures")
os.environ.setdefault("BRAIN_MODE", "mock")

import aria.main as main_mod  # noqa: E402
from aria import config, safety  # noqa: E402
from aria.models import MarketSnapshot, PortfolioState, Position  # noqa: E402
from aria.state.db import Store  # noqa: E402

GOOD_VOL = "120.5 M"   # comfortably above NR_MIN_LIQUIDITY_USD


def snapshot(fg: int, label: str, narrative_pct_7d: str, ts: datetime) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=ts,
        fear_greed_index=fg,
        fear_greed_label=label,
        total_mcap_change_24h_pct=1.2 if fg >= 60 else -2.8,
        total_mcap_change_7d_pct=6.4 if fg >= 60 else -9.1,
        narratives=[{
            "trendingRank": 1,
            "categoryName": "AI Agents",
            "marketCapChangePercentage7d": narrative_pct_7d,
            "topCoinList": {"headers": ["coinSymbol"], "rows": [["FET"], ["INJ"], ["CAKE"]]},
        }],
        token_quotes={
            "FET": {"symbol": "FET", "price": 1.42, "volume_24h": GOOD_VOL,
                    "percent_change_7d": 18.2},
            "INJ": {"symbol": "INJ", "price": 21.7, "volume_24h": GOOD_VOL},
            "CAKE": {"symbol": "CAKE", "price": 1.33, "volume_24h": GOOD_VOL},
            "USDT": {"symbol": "USDT", "price": 1.0, "volume_24h": GOOD_VOL},
        },
        raw={"source": "replay-scenario"},
    )


# The scripted week: (day_offset_hours, portfolio_value, fg, label, narrative_7d, note)
SCRIPT = [
    (0,   100.0, 68, "Greed",        "+9.4%",  "calm open — trending, agent enters the top narrative"),
    (12,  103.2, 71, "Greed",        "+12.1%", "position working"),
    (24,  106.8, 74, "Greed",        "+14.0%", "trend continues"),
    (36,  108.0, 66, "Greed",        "+7.2%",  "peak of the week"),
    (48,  104.5, 48, "Neutral",      "+1.3%",  "momentum fading -> ranging, stand aside"),
    (60,  101.0, 41, "Neutral",      "-0.8%",  "chop — holds, no forced trades"),
    (72,   97.5, 22, "Extreme fear", "-6.5%",  "regime flips high-risk -> close to stables"),
    (84,   95.0, 17, "Extreme fear", "-9.8%",  "risk-off persists, sitting in USDT"),
    (96,   86.0, 12, "Extreme fear", "-15.2%", "flash leg down: drawdown 20.4% -> CIRCUIT BREAKER"),
    (108,  86.5, 14, "Extreme fear", "-12.0%", "halted — only the latch speaks now"),
    (120,  87.0, 19, "Extreme fear", "-8.4%",  "still halted; heartbeat keeps the daily-trade rule"),
]

HOLDING = Position(token_symbol="FET", amount=70.4, entry_price_usd=1.42,
                   stop_loss_pct=6.0, opened_at=datetime.now(timezone.utc))


async def run() -> None:
    db_path = Path(os.environ["ARIA_DB"])
    if db_path.exists():
        db_path.unlink()
    store = Store(db_path)
    start = datetime.now(timezone.utc) - timedelta(days=6)
    peak = 0.0

    for i, (hours, value, fg, label, n7d, note) in enumerate(SCRIPT):
        ts = start + timedelta(hours=hours)
        peak = max(peak, value)
        in_position = 4 <= i < 7 or i in (1, 2, 3)  # holding FET between entry and close

        portfolio = PortfolioState(
            timestamp=ts,
            total_value_usd=value,
            peak_value_usd=peak,
            positions=[HOLDING] if 1 <= i <= 6 else [],
            stable_balance_usd=value if not in_position else value * 0.9,
            trades_today=0,
        )
        snap = snapshot(fg, label, n7d, ts)

        async def fake_load(*a, **k):
            return portfolio

        async def fake_fetch():
            return snap

        main_mod.load_portfolio = fake_load            # type: ignore[assignment]
        main_mod.signals.fetch_snapshot = fake_fetch   # type: ignore[assignment]

        print(f"[{i:02d}] {ts:%m-%d %H:%M} ${value:6.1f} F&G={fg:2d} dd={portfolio.drawdown_pct:4.1f}%  {note}")
        await main_mod.run_cycle(store, dry_run=True)

    print("\nhalted:", safety.is_halted(store), "|", safety.halt_reason(store)[:80])
    print("decisions:", store.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])
    for row in store.conn.execute(
        "SELECT regime, mode, action, safety_verdict FROM decisions ORDER BY timestamp"
    ):
        print("  ", row)
    print(f"\nreplay DB ready: {db_path}")
    print("view it:  ARIA_DB=replay.sqlite3 .venv/bin/uvicorn aria.api:app --port 8000")


if __name__ == "__main__":
    asyncio.run(run())
