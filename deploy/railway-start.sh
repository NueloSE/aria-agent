#!/usr/bin/env bash
# Railway entrypoint: run the dashboard API AND the agent loop in one service so they
# share the /data volume (the SQLite file the API reads is written by the loop).
#
# The API is the service's lifeline — it must stay up so the dashboard never 502s.
# So we SUPERVISE the agent separately: if the agent crashes, we restart it in place
# (with a short backoff) WITHOUT touching the API. Only if the API itself dies do we
# recycle the whole service. On SIGTERM (a redeploy) we stop both cleanly.
set -uo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
PY="${PYTHON:-python}"   # Railway's nixpython provides `python`; override locally
AGENT_RESTART_SEC="${AGENT_RESTART_SEC:-10}"

# Keep the agent alive without taking the API down with it.
agent_supervisor() {
  while true; do
    echo "[railway-start] launching agent loop…"
    "$PY" -m aria.main --loop || true
    echo "[railway-start] agent exited — restarting in ${AGENT_RESTART_SEC}s (API stays up)"
    sleep "${AGENT_RESTART_SEC}"
  done
}

agent_supervisor &
SUP_PID=$!

echo "[railway-start] serving dashboard API on 0.0.0.0:${PORT}…"
"$PY" -m uvicorn aria.api:app --host 0.0.0.0 --port "${PORT}" &
API_PID=$!

trap 'kill "$SUP_PID" "$API_PID" 2>/dev/null || true' EXIT INT TERM

# Wait specifically on the API. The agent restarting never reaches here.
wait "$API_PID"
echo "[railway-start] API exited — recycling the service"
kill "$SUP_PID" 2>/dev/null || true
exit 1
