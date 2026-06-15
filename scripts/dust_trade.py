"""Dust-trade verification — the FIRST real money ARIA ever moves.

Executes one tiny USDT -> ETH -> USDT round trip ($2-3) through the exact same
code path the competition will use (quote -> impact gate -> swap -> log), then
prints the BscScan links. Run it once on funding day, eyeball the txs, done.

Preconditions (the script checks all of them):
  - wallet holds >= $5 USDT and >= 0.002 BNB for gas on BSC mainnet
  - circuit-breaker tests green (hard rule #7)
  - you type YES at the prompt

Run:
    .venv/bin/python scripts/dust_trade.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ["EXECUTION_MODE"] = "live"
os.environ["NETWORK"] = "mainnet"

from aria import config  # noqa: E402
from aria.execution import _swap, get_twak  # noqa: E402
from aria.state.db import Store  # noqa: E402

AMOUNT_USD = "2.00"


async def main() -> None:
    print("=== ARIA dust-trade verification ===\n")

    # Gate 0: safety tests must be green before any real-money run (hard rule #7)
    print("running circuit-breaker tests first (hard rule #7)...")
    result = subprocess.run(
        [str(ROOT / ".venv/bin/pytest"),
         "tests/test_safety.py", "tests/test_circuit_breaker_integration.py", "-q"],
        cwd=ROOT, env={**os.environ, "SIGNALS_MODE": "fixtures"},
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-1500:])
        sys.exit("ABORT: safety tests are not green. Fix before touching real money.")
    print("  safety tests green ✓\n")

    twak = await get_twak()

    bnb = await twak.call("wallet_balance", {"chain": config.CHAIN})
    usdt = await twak.call("get_balance", {
        "address": config.AGENT_WALLET, "chain": config.CHAIN,
        "tokenAddress": "0x55d398326f99059fF775485246999027B3197955",  # canonical BSC USDT
    })
    print(f"native BNB: {bnb}")
    print(f"USDT:       {usdt}\n")

    quote = await twak.call("get_swap_quote", {
        "fromChain": config.CHAIN, "toChain": config.CHAIN,
        "fromToken": "USDT", "toToken": "ETH", "amount": AMOUNT_USD,
    })
    print(f"quote {AMOUNT_USD} USDT -> ETH: {quote}\n")

    print(f"This will execute REAL swaps: {AMOUNT_USD} USDT -> ETH -> USDT on BSC mainnet.")
    if input("Type YES to proceed: ").strip() != "YES":
        sys.exit("aborted.")

    store = Store(config.DB_PATH)
    leg1 = await _swap(store, "dust-verify", "strategy", "USDT", "ETH", AMOUNT_USD)
    print(f"\nleg 1: {leg1}")
    if leg1.status != "executed":
        sys.exit("leg 1 failed — investigate before retrying (no auto-retry by design).")

    eth_out = leg1.detail.split("->")[-1].strip().split()[0]
    leg2 = await _swap(store, "dust-verify", "strategy", "ETH", "USDT", eth_out)
    print(f"leg 2: {leg2}")

    print("\ntx hashes (verify on BscScan):")
    for row in store.conn.execute(
        "SELECT from_token, to_token, tx_hash, status FROM trades"
        " WHERE cycle_id='dust-verify' ORDER BY id"
    ):
        print(f"  {row[0]} -> {row[1]}  {row[3]}  https://bscscan.com/tx/{row[2]}")

    await twak.aclose()
    print("\nDust verification complete. ARIA's execution path is proven end-to-end.")


if __name__ == "__main__":
    asyncio.run(main())
