"""Async MCP client for a long-lived `twak serve` subprocess (stdio transport).

Protocol facts observed by probing (2026-06-12, twak v0.18.0):
- newline-delimited JSON-RPC over stdio
- responses can arrive OUT OF ORDER -> futures matched by request id
- tool results wrap JSON (or plain text) in result.content[0].text
- tool errors come back as isError=true with a JSON {code, message} body
Schemas: docs/vendor/trust-wallet-agent-kit/observed-tools.json
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from aria import config

log = logging.getLogger("aria.execution.twak")


class TwakError(Exception):
    pass


def parse_tool_result(msg: dict) -> Any:
    """Pure: JSON-RPC response message -> inner payload. Raises TwakError on
    rpc errors or isError results. Unit-test target."""
    if "error" in msg:
        raise TwakError(f"rpc error: {msg['error']}")
    result = msg.get("result", {})
    try:
        text = result["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TwakError(f"unexpected envelope: {str(result)[:300]}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = text
    if result.get("isError"):
        raise TwakError(f"tool error: {str(payload)[:500]}")
    return payload


class TwakClient:
    def __init__(self, password: Optional[str] = None):
        self._password = password or config.TWAK_WALLET_PASSWORD
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._rpc_id = 0
        self._write_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.running:
            return
        self._proc = await asyncio.create_subprocess_exec(
            "twak", "serve", "--password", self._password,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "aria-agent", "version": "0.1"},
        })
        await self._notify("notifications/initialized")
        log.info("twak serve started (pid %s)", self._proc.pid)

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:  # subprocess died
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(TwakError("twak serve exited"))
                self._pending.clear()
                return
            raw = line.decode().strip()
            if not raw.startswith("{"):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            fut = self._pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def _send(self, payload: dict) -> None:
        assert self._proc and self._proc.stdin
        async with self._write_lock:
            self._proc.stdin.write((json.dumps(payload) + "\n").encode())
            await self._proc.stdin.drain()

    async def _notify(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _request(self, method: str, params: dict, timeout: float = 120.0) -> dict:
        self._rpc_id += 1
        rpc_id = self._rpc_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rpc_id] = fut
        await self._send({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rpc_id, None)

    async def call(self, tool: str, arguments: Optional[dict] = None,
                   timeout: float = 120.0) -> Any:
        if not self.running:
            await self.start()
        msg = await self._request(
            "tools/call", {"name": tool, "arguments": arguments or {}}, timeout
        )
        return parse_tool_result(msg)

    async def aclose(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 10)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
