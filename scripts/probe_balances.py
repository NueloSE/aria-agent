"""Dump the raw get_balance response shape for held tokens, so we can implement an
accurate on-chain reconcile (no guessed decimals in real-money valuation code).

Read-only: only reads balances, moves nothing.

Run:
    TWAK_WALLET_PASSWORD=yourpw .venv/bin/python scripts/probe_balances.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["EXECUTION_MODE"] = "live"
os.environ["NETWORK"] = "mainnet"

from aria import config  # noqa: E402
from aria.execution import get_twak, _BSC_CONTRACTS  # noqa: E402

# Tokens you actually hold (per BscScan) + USDT as the known-good 18-decimal baseline.
CHECK = ["USDT", "ADA", "DOT", "AVAX", "DOGE", "ETH", "SHIB", "BTT"]


async def main() -> None:
    twak = await get_twak()
    print("=== raw get_balance responses (read-only) ===\n")
    for sym in CHECK:
        addr = _BSC_CONTRACTS.get(sym)
        if not addr:
            print(f"{sym}: no contract on file"); continue
        try:
            r = await twak.call("get_balance", {
                "address": config.AGENT_WALLET, "chain": config.CHAIN,
                "tokenAddress": addr,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"{sym}: ERROR {exc}"); continue
        # Print the full structure so we can see exactly which field holds the
        # human-readable amount (formatted/uiAmount) vs the raw atomic units.
        print(f"--- {sym} ({addr}) ---")
        print(json.dumps(r, indent=2)[:700])
        print()
    await twak.aclose()


if __name__ == "__main__":
    asyncio.run(main())
