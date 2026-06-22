"""Probe which TRADEABLE_SYMBOLS TWAK can actually SWAP on BSC.

Read-only: fetches a USDT -> TOKEN swap QUOTE for every token in
config.TRADEABLE_SYMBOLS and reports which ones TWAK recognizes. No swaps are
executed, no money moves — quotes don't sign or send anything.

Why: a token having a BSC contract (so get_balance works) does NOT mean TWAK's
swap aggregator supports trading it by symbol. BCH/BTT return TOKEN_NOT_FOUND.
This tells us the REAL tradeable universe so TRADEABLE_SYMBOLS can be narrowed to
exactly the swappable set — no wasted cycles, no 6h re-check churn.

Run (needs your local twak setup + wallet password):
    TWAK_WALLET_PASSWORD=yourpw .venv/bin/python scripts/probe_swappable.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# get_twak() only connects to the real chain in live/mainnet mode.
os.environ["EXECUTION_MODE"] = "live"
os.environ["NETWORK"] = "mainnet"

from aria import config  # noqa: E402
from aria.execution import get_twak, _BSC_CONTRACTS  # noqa: E402
from aria.execution.twak_client import TwakError  # noqa: E402

AMOUNT_USD = "2.00"   # realistic non-dust size for the quote


async def _quote(twak, to_token: str) -> "tuple[bool, str]":
    """Return (ok, detail). ok=True means TWAK produced a real route."""
    try:
        q = await twak.call("get_swap_quote", {
            "fromChain": config.CHAIN, "toChain": config.CHAIN,
            "fromToken": "USDT", "toToken": to_token, "amount": AMOUNT_USD,
        })
    except TwakError as exc:
        return False, f"call error: {str(exc)[:70]}"
    if isinstance(q, dict) and q.get("success") is not False:
        return True, str(q.get("output") or q.get("summary") or "ok")[:50]
    code = q.get("code") if isinstance(q, dict) else "?"
    return False, str(code)


async def main() -> None:
    tokens = sorted(config.TRADEABLE_SYMBOLS)
    print(f"=== Probing {len(tokens)} tokens: by SYMBOL, then by CONTRACT ADDRESS ===")
    print(f"(quote-only at ${AMOUNT_USD}, no swaps executed)\n")

    twak = await get_twak()

    by_symbol: list[str] = []      # works with plain symbol
    by_address: list[str] = []     # only works via contract address
    dead: list[str] = []           # no route either way

    print(f"  {'TOKEN':6} {'SYMBOL':<10} {'ADDRESS':<10} detail")
    for sym in tokens:
        ok_sym, d_sym = await _quote(twak, sym)
        if ok_sym:
            by_symbol.append(sym)
            print(f"  {sym:6} {'OK':<10} {'-':<10} {d_sym}")
            continue
        # symbol failed — retry by contract address
        addr = _BSC_CONTRACTS.get(sym)
        if not addr:
            dead.append(sym)
            print(f"  {sym:6} {d_sym:<10} {'no-addr':<10}")
            continue
        ok_addr, d_addr = await _quote(twak, addr)
        if ok_addr:
            by_address.append(sym)
            print(f"  {sym:6} {d_sym:<10} {'OK':<10} {d_addr}")
        else:
            dead.append(sym)
            print(f"  {sym:6} {d_sym:<10} {d_addr:<10}")

    total = by_symbol + by_address
    print("\n=== RESULT ===")
    print(f"Works by SYMBOL  ({len(by_symbol)}): {', '.join(by_symbol) or 'none'}")
    print(f"Works by ADDRESS ({len(by_address)}): {', '.join(by_address) or 'none'}")
    print(f"DEAD - no route  ({len(dead)}): {', '.join(dead) or 'none'}")
    print(f"\nTOTAL tradeable: {len(total)} -> {', '.join(sorted(total))}")

    if by_address:
        print("\n>>> Some tokens ONLY route by contract address. Tell Claude — the swap")
        print(">>> path needs to pass addresses for these, which unlocks them all.")

    print("\n=== TRADEABLE_SYMBOLS (everything that routed, either way) ===")
    quoted = ", ".join(f'"{s}"' for s in sorted(total))
    print(f"TRADEABLE_SYMBOLS: frozenset[str] = frozenset({{{quoted}}})")

    await twak.aclose()


if __name__ == "__main__":
    asyncio.run(main())
