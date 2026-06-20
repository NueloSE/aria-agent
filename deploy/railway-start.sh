#!/usr/bin/env bash
# Railway entrypoint: run the agent loop AND the dashboard API in one service so
# they share the /data volume (the SQLite file the API reads is written by the loop).
#
# Both run as children of this script. If EITHER exits we tear the whole service
# down with a non-zero status so Railway's restart policy recycles it cleanly,
# rather than leaving the API serving a stale DB (or the agent running headless).
set -uo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
PY="${PYTHON:-python}"   # Railway's nixpython provides `python`; override locally

echo "[railway-start] launching agent loop…"
"$PY" -m aria.main --loop &
AGENT_PID=$!

echo "[railway-start] serving dashboard API on 0.0.0.0:${PORT}…"
"$PY" -m uvicorn aria.api:app --host 0.0.0.0 --port "${PORT}" &
API_PID=$!

# Bring both down on signal, and on either child dying.
trap 'kill "$AGENT_PID" "$API_PID" 2>/dev/null || true' EXIT INT TERM

while kill -0 "$AGENT_PID" 2>/dev/null && kill -0 "$API_PID" 2>/dev/null; do
  sleep 5
done

echo "[railway-start] a process exited — shutting the service down for a clean restart"
exit 1
