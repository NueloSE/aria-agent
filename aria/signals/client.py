"""Signal layer: composes a MarketSnapshot from CMC Agent Hub data.
Signals only — no trading logic lives here.

Two sources, ONE composer (so fixture tests exercise the same parsing as live):
  - live:     async MCP calls via CMCClient (SIGNALS_MODE=live)
  - fixtures: tests/fixtures/cmc_*.json captured in Stage 1 (SIGNALS_MODE=fixtures)

Failure policy (docs/DESIGN.md): required signals failing -> SignalError -> caller skips
the cycle; 3 consecutive failures -> caller forces preservation. Optional signals
failing -> warn and continue with empty fields.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aria import config
from aria.models import MarketSnapshot
from aria.signals.cmc_client import CMCClient, SignalError
from aria.signals.parsing import parse_pct, rows_to_dicts

log = logging.getLogger("aria.signals")

FIXTURES = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"

_client: Optional[CMCClient] = None


def _get_client() -> CMCClient:
    global _client
    if _client is None:
        _client = CMCClient()
    return _client


# --- Composition (shared by live + fixtures) --------------------------------

def _normalize_quotes(payload: Any) -> list[dict]:
    """Quotes arrive as a LIST of dicts (single id) or a headers/rows TABLE (multi-id)."""
    if isinstance(payload, list):
        return [q for q in payload if isinstance(q, dict)]
    if isinstance(payload, dict) and "headers" in payload:
        return rows_to_dicts(payload)
    if isinstance(payload, dict):
        return [payload]
    return []


def _normalize_macro(payload: Any) -> list[dict]:
    """Macro events arrive as a dict of named headers/rows tables
    (e.g. {'upcomingEventNews': {headers, rows}}). Flatten, tagging the source."""
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    events: list[dict] = []
    if isinstance(payload, dict):
        for source, table in payload.items():
            for row in rows_to_dicts(table):
                row["_source"] = source
                events.append(row)
    return events


def compose_snapshot(
    global_metrics: dict,
    narratives_payload: dict,
    quotes: Any,
    mcap_ta: Optional[dict] = None,
    derivatives: Optional[dict] = None,
    macro_events: Optional[Any] = None,
) -> MarketSnapshot:
    sentiment = (global_metrics.get("sentiment", {}) or {}).get("fear_greed", {}).get("current", {})
    mcap = (global_metrics.get("market_size", {}) or {}).get("total_crypto_market_cap_usd", {})
    changes = mcap.get("percent_change", {}) or {}

    narratives = rows_to_dicts((narratives_payload or {}).get("categoryList", {}))

    token_quotes = {
        str(q.get("symbol", "")).upper(): q
        for q in _normalize_quotes(quotes)
        if q.get("symbol")
    }

    return MarketSnapshot(
        timestamp=datetime.now(timezone.utc),
        fear_greed_index=sentiment.get("index"),
        fear_greed_label=sentiment.get("value"),
        total_mcap_change_24h_pct=parse_pct(changes.get("24h")),
        total_mcap_change_7d_pct=parse_pct(changes.get("7d")),
        mcap_ta=mcap_ta or {},
        derivatives=derivatives or {},
        narratives=narratives,
        macro_events=_normalize_macro(macro_events),
        token_quotes=token_quotes,
        raw={"global_metrics": global_metrics},
    )


# --- Live path ---------------------------------------------------------------

async def _fetch_live() -> MarketSnapshot:
    c = _get_client()

    universe = list(config.BLUE_CHIPS) + list(config.STABLES)
    ids = [i for s in universe if (i := await c.resolve_id(s)) is not None]

    # Required signals: failure aborts the snapshot (SignalError propagates)
    global_metrics, narratives_payload, quotes = await asyncio.gather(
        c.global_metrics(),
        c.trending_narratives(),
        c.quotes(ids),
    )

    # Optional signals: degrade gracefully
    async def optional(coro: Any, name: str) -> Optional[Any]:
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            log.warning("optional signal %s failed: %s", name, exc)
            return None

    mcap_ta, derivatives, macro = await asyncio.gather(
        optional(c.mcap_technical_analysis(), "mcap_ta"),
        optional(c.derivatives(), "derivatives"),
        optional(c.macro_events(), "macro_events"),
    )

    snap = compose_snapshot(global_metrics, narratives_payload, quotes,
                            mcap_ta, derivatives, macro)
    log.info("live snapshot ok | credits this run: %d", c.calls_made)
    return snap


# --- Fixtures path -----------------------------------------------------------

def _fixture_payload(name: str) -> Any:
    path = FIXTURES / f"cmc_{name}.json"
    if not path.exists():
        return None
    outer = json.loads(path.read_text())
    return json.loads(outer["result"]["content"][0]["text"])


def fetch_snapshot_from_fixtures() -> MarketSnapshot:
    return compose_snapshot(
        global_metrics=_fixture_payload("get_global_metrics_latest") or {},
        narratives_payload=_fixture_payload("trending_crypto_narratives") or {},
        quotes=_fixture_payload("get_crypto_quotes_latest"),  # raw — composer normalizes
        mcap_ta=_fixture_payload("get_crypto_marketcap_technical_analysis"),
        derivatives=_fixture_payload("get_global_crypto_derivatives_metrics"),
        macro_events=_fixture_payload("get_upcoming_macro_events"),
    )


# --- Candidate enrichment (strategy support) ---------------------------------

async def quotes_for(symbols: list[str]) -> dict[str, dict]:
    """Quotes for arbitrary symbols (e.g. narrative candidates outside the core
    universe). Live mode only — in fixtures mode returns {} and strategies'
    no-quote-data gate conservatively excludes the candidate."""
    if config.SIGNALS_MODE == "fixtures" or not symbols:
        return {}
    c = _get_client()
    ids = [i for s in symbols if (i := await c.resolve_id(s)) is not None]
    if not ids:
        return {}
    payload = await c.quotes(ids)
    return {
        str(q.get("symbol", "")).upper(): q
        for q in _normalize_quotes(payload)
        if q.get("symbol")
    }


# --- Quotes-only (the fast loop's per-tick fetch: ONE credit) -------------------

async def fetch_quotes_only() -> dict[str, dict]:
    """Just the tracked-universe quotes — one batched CMC call (1 credit), no macro.
    This is what the 30s fast loop polls; the expensive macro read is cached and
    refreshed separately (see aria.regime). Returns {symbol -> quote fields}."""
    if config.SIGNALS_MODE == "fixtures":
        return fetch_snapshot_from_fixtures().token_quotes
    c = _get_client()
    universe = list(config.BLUE_CHIPS) + list(config.STABLES)
    ids = [i for s in universe if (i := await c.resolve_id(s)) is not None]
    if not ids:
        return {}
    payload = await c.quotes(ids)
    return {
        str(q.get("symbol", "")).upper(): q
        for q in _normalize_quotes(payload)
        if q.get("symbol")
    }


# --- Entry point ---------------------------------------------------------------

async def fetch_snapshot() -> MarketSnapshot:
    if config.SIGNALS_MODE == "fixtures":
        return fetch_snapshot_from_fixtures()
    return await _fetch_live()
