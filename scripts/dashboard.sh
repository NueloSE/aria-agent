#!/usr/bin/env bash
# One command to view the dashboard: builds the UI and serves it together with the
# API on a single port. Then open  http://localhost:8000/dashboard
#
#   ./scripts/dashboard.sh                 # build + serve on :8000 (paper.sqlite3)
#   ARIA_DB=aria.sqlite3 ./scripts/dashboard.sh   # point at a different DB
#   REBUILD=0 ./scripts/dashboard.sh       # skip the rebuild, serve the existing build
#
# This only VIEWS state — the agent itself runs separately (./scripts/paper_trade.sh).
set -u
cd "$(dirname "$0")/.."

export ARIA_DB="${ARIA_DB:-paper.sqlite3}"
PORT="${PORT:-8000}"

if [ "${REBUILD:-1}" = "1" ] || [ ! -f dashboard/dist/index.html ]; then
  echo "[dashboard] building UI…"
  ( cd dashboard && npm run build ) || { echo "[dashboard] build failed"; exit 1; }
fi

echo "[dashboard] serving UI + API for $ARIA_DB"
echo "[dashboard] → open  http://localhost:$PORT/dashboard   (Ctrl-C to stop)"
exec .venv/bin/uvicorn aria.api:app --port "$PORT"
