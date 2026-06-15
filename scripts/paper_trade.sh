#!/usr/bin/env bash
# Paper-trading forward simulation — real decisions on LIVE signals, simulated
# fills at market price + simulated cost. No funds, no chain. Writes to its own
# paper.sqlite3 so it never touches the real soak DB.
#
#   ./scripts/paper_trade.sh            # mock brain (free) — holds in fearful markets
#   BRAIN_MODE=live ./scripts/paper_trade.sh   # real Claude brain (needs Anthropic credits)
#
# View it (separate terminal):
#   ARIA_DB=paper.sqlite3 .venv/bin/uvicorn aria.api:app --port 8000
#   cd dashboard && npm run dev    -> http://localhost:5173/dashboard
set -u
cd "$(dirname "$0")/.."

export EXECUTION_MODE=paper
export SIGNALS_MODE=live
export ARIA_DB="${ARIA_DB:-paper.sqlite3}"
export BRAIN_MODE="${BRAIN_MODE:-mock}"

echo "[paper] brain=$BRAIN_MODE db=$ARIA_DB — simulated fills on live signals, no funds"
exec .venv/bin/python -m aria.main --loop      # NOT --dry-run: paper fills are the point
