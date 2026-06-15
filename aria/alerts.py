"""Operator alerts. Telegram if configured, log-only otherwise — the agent must
never fail because alerting failed.

Setup (free, ~2 min):
  1. Telegram: message @BotFather -> /newbot -> copy the token
  2. Message your new bot once, then GET https://api.telegram.org/bot<TOKEN>/getUpdates
     and read your chat id from the response
  3. .env:  TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

log = logging.getLogger("aria.alerts")

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def configured() -> bool:
    return bool(_TOKEN and _CHAT)


async def send(message: str) -> None:
    """Fire-and-forget operator alert. Never raises."""
    log.warning("ALERT: %s", message)
    if not configured():
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
                json={"chat_id": _CHAT, "text": f"🤖 ARIA\n{message}"},
            )
    except Exception as exc:  # noqa: BLE001 — alerting must never take the agent down
        log.error("telegram alert failed: %s", exc)


def send_sync(message: str) -> None:
    """For non-async callsites; schedules if a loop is running."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send(message))
    except RuntimeError:
        asyncio.run(send(message))
