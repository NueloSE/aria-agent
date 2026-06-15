#!/usr/bin/env bash
# ARIA supervisor — restarts the agent on crash, with backoff. Use during the
# competition week (on the server, inside tmux/screen or a systemd unit).
#
#   ./scripts/run_agent.sh                 # live loop (respects .env gates)
#   DRY_RUN=1 ./scripts/run_agent.sh       # supervised dry-run (soak testing)
#
# On startup after a crash, the agent reconciles on-chain balances before
# trading (never trusts stale local state) — that's why blind restarts are safe.
set -u
cd "$(dirname "$0")/.."

PY=.venv/bin/python
ARGS="--loop"
[ "${DRY_RUN:-0}" = "1" ] && ARGS="--dry-run --loop"

BACKOFF=5
while true; do
  echo "[supervisor] $(date -u +%FT%TZ) starting: aria.main $ARGS"
  $PY -m aria.main $ARGS
  CODE=$?
  echo "[supervisor] $(date -u +%FT%TZ) agent exited code=$CODE — restarting in ${BACKOFF}s"
  sleep "$BACKOFF"
  # exponential backoff capped at 5 min so a hard crash-loop can't spin
  BACKOFF=$(( BACKOFF * 2 > 300 ? 300 : BACKOFF * 2 ))
done
