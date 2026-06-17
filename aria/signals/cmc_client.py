"""Async client for the CMC Agent Hub MCP server.

Protocol facts observed in Stage-1 probing (2026-06-12):
- Endpoint https://mcp.coinmarketcap.com/mcp, auth header X-CMC-MCP-API-KEY
- Server is effectively stateless (no Mcp-Session-Id returned) but we still send
  the initialize handshake per MCP spec
- Responses may be application/json OR text/event-stream (SSE) — handle both
- Tool results wrap a JSON string in result.content[0].text — parse twice
- Cost: 1 credit per tools/call; free plan = 50 req/min, 15k credits/month
Schemas: docs/vendor/cmc-agent-hub/observed-tools.json
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from aria import config

log = logging.getLogger("aria.signals.cmc")

_IDS_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cmc_ids.json"


class SignalError(Exception):
    pass


def _is_transient(detail: str) -> bool:
    """A CMC tool-level error worth retrying (server-side 5xx / rate limit / timeout),
    as opposed to a genuine bad request we should not hammer."""
    d = detail.lower()
    return any(s in d for s in ("internal server error", '"code":500', "'code': 500",
                                "502", "503", "504", "429", "timeout", "temporarily"))


class CMCClient:
    def __init__(self, api_key: Optional[str] = None, url: Optional[str] = None):
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-CMC-MCP-API-KEY": api_key or config.CMC_MCP_API_KEY,
        }
        self._url = url or config.CMC_MCP_URL
        self._http = httpx.AsyncClient(timeout=config.SIGNAL_TIMEOUT_S)
        self._initialized = False
        self._rpc_id = 0
        self.calls_made = 0
        self._id_cache: dict[str, int] = self._load_id_cache()
        # Symbols CMC can't resolve (e.g. ROSE/ZETA/BRETT) — remembered for this
        # process so the fast loop doesn't re-search them (a credit leak) every tick.
        self._unresolved: set[str] = set()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- MCP plumbing -------------------------------------------------------

    async def _post(self, payload: dict) -> Optional[dict]:
        resp = await self._http.post(self._url, json=payload, headers=self._headers)
        resp.raise_for_status()
        body = resp.text
        if not body.strip():
            return None
        if "text/event-stream" in resp.headers.get("content-type", ""):
            result = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    try:
                        result = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            return result
        return resp.json()

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._rpc_id += 1
        await self._post({
            "jsonrpc": "2.0", "id": self._rpc_id, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "aria-agent", "version": "0.1"},
            },
        })
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True

    async def call(self, tool: str, arguments: Optional[dict] = None) -> Any:
        """Call a tool; return the inner (double-decoded) payload.

        Transient failures (transport blips, CMC 5xx) are retried in-place with
        backoff so a one-off hiccup never registers as a signal failure. Non-transient
        errors (rpc errors, real tool errors, malformed envelopes) raise immediately."""
        last_exc: Optional[SignalError] = None
        for attempt in range(max(1, config.SIGNAL_RETRY_ATTEMPTS)):
            if attempt:
                await asyncio.sleep(config.SIGNAL_RETRY_BACKOFF_S * attempt)
            try:
                await self._ensure_initialized()  # idempotent; retried if it blipped
                self._rpc_id += 1
                msg = await self._post({
                    "jsonrpc": "2.0", "id": self._rpc_id, "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments or {}},
                })
            except httpx.HTTPError as exc:
                last_exc = SignalError(f"{tool}: transport error: {exc}")
                continue  # transient — retry
            self.calls_made += 1
            if not msg:
                last_exc = SignalError(f"{tool}: empty response")
                continue  # transient — retry
            if "error" in msg:
                raise SignalError(f"{tool}: rpc error: {msg['error']}")
            result = msg.get("result", {})
            if result.get("isError"):
                detail = str(result)
                if _is_transient(detail):
                    last_exc = SignalError(f"{tool}: tool error: {detail[:300]}")
                    continue  # CMC 5xx — retry
                raise SignalError(f"{tool}: tool error: {detail[:300]}")
            try:
                text = result["content"][0]["text"]
            except (KeyError, IndexError) as exc:
                raise SignalError(f"{tool}: unexpected envelope: {str(result)[:300]}") from exc
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text  # a few tools may return plain text
        raise last_exc or SignalError(f"{tool}: failed after retries")

    # --- Symbol -> CMC id resolution (cached, write-through) ----------------

    def _load_id_cache(self) -> dict[str, int]:
        if _IDS_CACHE_PATH.exists():
            return {k: int(v) for k, v in json.loads(_IDS_CACHE_PATH.read_text()).items()}
        return {}

    def _save_id_cache(self) -> None:
        _IDS_CACHE_PATH.write_text(json.dumps(self._id_cache, indent=2, sort_keys=True))

    async def resolve_id(self, symbol: str) -> Optional[int]:
        if symbol in self._id_cache:
            return self._id_cache[symbol]
        if symbol in self._unresolved:
            return None  # known-unresolvable — don't re-spend a search credit every tick
        # live API enforces limit <= 5 (observed 2026-06-12)
        results = await self.call("search_cryptos", {"query": symbol, "limit": 5})
        if isinstance(results, list):
            exact = [r for r in results if str(r.get("symbol", "")).upper() == symbol.upper()]
            best = min(exact, key=lambda r: r.get("rank") or 10**9) if exact else None
            if best:
                self._id_cache[symbol] = int(best["id"])
                self._save_id_cache()
                return self._id_cache[symbol]
        self._unresolved.add(symbol)
        log.warning("could not resolve CMC id for %s (won't retry this session)", symbol)
        return None

    # --- One method per signal ----------------------------------------------

    async def global_metrics(self) -> dict:
        return await self.call("get_global_metrics_latest")

    async def mcap_technical_analysis(self) -> dict:
        return await self.call("get_crypto_marketcap_technical_analysis")

    async def derivatives(self) -> dict:
        return await self.call("get_global_crypto_derivatives_metrics")

    async def trending_narratives(self) -> dict:
        return await self.call("trending_crypto_narratives")

    async def macro_events(self) -> Any:
        return await self.call("get_upcoming_macro_events")

    async def quotes(self, ids: list[int]) -> Any:
        """Raw payload: a LIST of dicts for one id, a headers/rows TABLE for several.
        compose_snapshot normalizes both."""
        return await self.call(
            "get_crypto_quotes_latest", {"id": ",".join(str(i) for i in ids)}
        )

    async def token_technical_analysis(self, cmc_id: int) -> dict:
        return await self.call("get_crypto_technical_analysis", {"id": cmc_id})
