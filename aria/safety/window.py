"""Competition trading window + operator override.

The organizers measure %-return between window start and end; trades outside the
window are pure cost. Per admin (2026-06-12): "the first trading day starts at the
exact same time the submission time ends" and WE start/stop the agent ourselves.

Sources of truth, in precedence order (checked every cycle — UI edits apply
within one cycle, no restart):
  1. trading_override in agent_state: "on" (trade regardless) / "off" (emergency stop)
  2. window_start_utc / window_end_utc in agent_state (set from the dashboard)
  3. COMPETITION_START_UTC / COMPETITION_END_UTC env (initial seed, optional)
  4. default: dev mode (stub execution) -> allowed; LIVE mode -> DENIED.
     Real money with no window configured is an operator error, not a default.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from aria import config
from aria.state.db import Store

log = logging.getLogger("aria.safety.window")

KEY_START = "window_start_utc"
KEY_END = "window_end_utc"
KEY_OVERRIDE = "trading_override"   # "on" | "off" | absent


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        log.error("unparseable window timestamp: %r", raw)
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def get_window(store: Store) -> tuple[Optional[datetime], Optional[datetime]]:
    """DB (dashboard-set) wins; env is only the initial seed."""
    start = _parse_ts(store.get_state(KEY_START)) or _parse_ts(os.getenv("COMPETITION_START_UTC"))
    end = _parse_ts(store.get_state(KEY_END)) or _parse_ts(os.getenv("COMPETITION_END_UTC"))
    return start, end


def set_window(store: Store, start: Optional[str], end: Optional[str]) -> None:
    """Called by the dashboard. Values are validated before storing; every change
    is in agent_state with an updated_at timestamp (the audit trail)."""
    for key, raw in ((KEY_START, start), (KEY_END, end)):
        if raw is None:
            continue
        if _parse_ts(raw) is None:
            raise ValueError(f"invalid timestamp for {key}: {raw!r}")
        store.set_state(key, raw)
        log.warning("window updated: %s = %s", key, raw)


def set_override(store: Store, value: Optional[str]) -> None:
    """'on' = trade regardless of window; 'off' = emergency stop; None = clear."""
    if value is None:
        store.clear_state(KEY_OVERRIDE)
        log.warning("trading override cleared — schedule rules again")
    elif value in ("on", "off"):
        store.set_state(KEY_OVERRIDE, value)
        log.warning("trading override set: %s", value)
    else:
        raise ValueError(f"override must be 'on', 'off' or None, got {value!r}")


def trading_allowed(store: Store, now: Optional[datetime] = None) -> tuple[bool, str]:
    """(allowed, reason). Checked every cycle before the brain runs."""
    now = now or datetime.now(timezone.utc)

    override = store.get_state(KEY_OVERRIDE)
    if override == "off":
        return False, "EMERGENCY STOP (operator override 'off')"
    if override == "on":
        return True, "operator override 'on'"

    start, end = get_window(store)
    if start is None and end is None:
        if config.EXECUTION_MODE == "live" and config.NETWORK == "mainnet":
            return False, "LIVE mode with no competition window configured — refusing to trade"
        return True, "dev mode, no window configured"
    if start and now < start:
        return False, f"before window start ({start.isoformat()})"
    if end and now >= end:
        return False, f"after window end ({end.isoformat()})"
    return True, "inside competition window"
