"""Resolve the eligible-list symbols to BSC contract addresses via the CMC REST API.

Why: TWAK's swap accepts a symbol OR an address. Symbols are ambiguous (the official
list literally contains two SLX tokens) — addresses are not. Execution should prefer
addresses for anything outside the blue-chip set.

Why REST and not the MCP info tool: probed 2026-06-12 — MCP get_crypto_info exposes
only the PRIMARY platform (CAKE shows its Ethereum contract, no BSC). The REST
/v2/cryptocurrency/info endpoint has the full multi-chain contract_address array,
and both endpoints batch (~5 credits total for the whole list).

Run:
    .venv/bin/python scripts/resolve_addresses.py
Output:
    aria/data/eligible_tokens_resolved.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aria import config  # noqa: E402

BASE = "https://pro-api.coinmarketcap.com"
HEADERS = {"X-CMC_PRO_API_KEY": config.CMC_MCP_API_KEY}
OUT = ROOT / "aria" / "data" / "eligible_tokens_resolved.json"
BSC_NAMES = ("bnb smart chain", "binance smart chain", "bnb chain", "bsc")


def get(path: str, **params) -> dict:
    r = httpx.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    body = r.json()
    if body.get("status", {}).get("error_code"):
        raise RuntimeError(body["status"])
    return body["data"]


def bsc_contracts(info: dict) -> list[str]:
    out = []
    for entry in info.get("contract_address", []) or []:
        platform = entry.get("platform", {}) or {}
        name = str(platform.get("name", "")).lower()
        coin_sym = str((platform.get("coin") or {}).get("symbol", "")).upper()
        if coin_sym == "BNB" or any(n in name for n in BSC_NAMES):
            addr = entry.get("contract_address")
            if addr:
                out.append(addr)
    return out


def main() -> None:
    symbols = json.loads(
        (ROOT / "aria" / "data" / "eligible_tokens.json").read_text()
    )["symbols"]

    # 1. symbol -> candidate CMC ids (map endpoint batches by comma list)
    candidates: dict[str, list[dict]] = {s: [] for s in symbols}
    ascii_syms = [s for s in symbols if s.isascii()]
    skipped = [s for s in symbols if not s.isascii()]
    for chunk_start in range(0, len(ascii_syms), 80):
        chunk = ascii_syms[chunk_start:chunk_start + 80]
        try:
            data = get("/v1/cryptocurrency/map", symbol=",".join(chunk), listing_status="active")
        except Exception as exc:  # noqa: BLE001 — fall back to per-symbol on a bad chunk
            print(f"chunk map failed ({exc}); falling back per-symbol")
            data = []
            for s in chunk:
                try:
                    data.extend(get("/v1/cryptocurrency/map", symbol=s, listing_status="active"))
                except Exception as exc2:  # noqa: BLE001
                    print(f"  map {s}: {exc2}")
                time.sleep(1.3)
        for item in data:
            sym = str(item.get("symbol", "")).upper()
            for orig in symbols:
                if orig.upper() == sym:
                    candidates[orig].append({"id": item["id"], "name": item["name"],
                                             "rank": item.get("rank")})
        time.sleep(1.3)

    all_ids = sorted({c["id"] for lst in candidates.values() for c in lst})
    print(f"map: {len(all_ids)} candidate ids for {len(symbols)} symbols "
          f"(skipped non-ascii: {skipped})")

    # 2. batched info -> multi-chain contract addresses
    info_by_id: dict[int, dict] = {}
    for chunk_start in range(0, len(all_ids), 100):
        chunk = all_ids[chunk_start:chunk_start + 100]
        data = get("/v2/cryptocurrency/info", id=",".join(map(str, chunk)),
                   aux="urls,platform")
        info_by_id.update({int(k): v for k, v in data.items()})
        time.sleep(1.3)

    # 3. pick the BSC deployment per symbol; flag ambiguity honestly
    resolved: dict[str, dict] = {}
    problems: list[str] = []
    for sym in symbols:
        hits = []
        for cand in candidates[sym]:
            info = info_by_id.get(cand["id"], {})
            for addr in bsc_contracts(info):
                hits.append({"cmc_id": cand["id"], "name": cand["name"],
                             "rank": cand["rank"], "bsc_address": addr})
        if not hits:
            problems.append(f"{sym}: no BSC contract found "
                            f"({len(candidates[sym])} CMC matches)")
            resolved[sym] = {"bsc_address": None, "candidates": candidates[sym][:3]}
            continue
        hits.sort(key=lambda h: h["rank"] if h["rank"] is not None else 10**9)
        best = hits[0]
        resolved[sym] = best
        if len({h["bsc_address"].lower() for h in hits}) > 1:
            resolved[sym]["ambiguous_alternatives"] = hits[1:4]
            problems.append(f"{sym}: AMBIGUOUS — {len(hits)} BSC tokens share the "
                            f"symbol; picked rank {best['rank']} ({best['name']})")

    ok = len([r for r in resolved.values() if r.get("bsc_address")])
    OUT.write_text(json.dumps({
        "_meta": {
            "generated_by": "scripts/resolve_addresses.py (CMC REST, 2026-06-12)",
            "note": "Execution must prefer bsc_address over symbol for swaps. "
                    "null bsc_address = treat as untradeable until manually verified.",
            "resolved": ok,
            "total": len(symbols),
            "problems": problems,
        },
        "tokens": resolved,
    }, indent=2, ensure_ascii=False))

    print(f"\nresolved {ok}/{len(symbols)} -> {OUT}")
    print(f"problems ({len(problems)}):")
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    main()
