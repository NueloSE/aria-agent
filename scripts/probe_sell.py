"""Diagnose why SELL swaps (TOKEN -> USDT) return an empty result.

Executes ONE real sell of a held token and dumps the RAW quote + swap result so we
can see exactly what TWAK returns (approval needed? success:false? different shape?).
This moves a small amount of real money (one sell, ~$1) — it also doubles as a real
exit, freeing a slot. You must type YES to proceed.

Run:
    TWAK_WALLET_PASSWORD=yourpw .venv/bin/python scripts/probe_sell.py DOGE
    (token symbol optional; defaults to DOGE)
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
from aria.execution import get_twak, _BSC_CONTRACTS, _token_ref  # noqa: E402

SYM = (sys.argv[1] if len(sys.argv) > 1 else "DOGE").upper()
USDT = _BSC_CONTRACTS["USDT"]


async def main() -> None:
    if SYM not in _BSC_CONTRACTS:
        sys.exit(f"{SYM} not in _BSC_CONTRACTS")
    twak = await get_twak()
    addr = _BSC_CONTRACTS[SYM]

    # 1) How much of SYM do we hold? Derive the human amount from raw + decimals
    #    (DOGE is 8 decimals on BSC, everything else 18 — confirmed via probe_balances).
    bal = await twak.call("get_balance", {
        "address": config.AGENT_WALLET, "chain": config.CHAIN, "tokenAddress": addr})
    print(f"=== {SYM} balance ===")
    print(json.dumps(bal, indent=2)[:500])
    raw = bal.get("amounts", {}).get("total", "0")
    decimals = 8 if SYM == "DOGE" else 18
    human = float(raw) / (10 ** decimals)
    if human <= 0:
        sys.exit(f"wallet holds 0 {SYM} — pass a token you actually hold")
    amount = f"{human * 0.99:.10f}".rstrip("0")  # sell 99% to dodge dust-rounding reverts
    print(f"\nholding {human} {SYM}; selling {amount} {SYM}\n")

    # 2) Quote the sell (read-only) — dump raw.
    print("=== get_swap_quote (SELL) raw ===")
    q = await twak.call("get_swap_quote", {
        "fromChain": config.CHAIN, "toChain": config.CHAIN,
        "fromToken": _token_ref(SYM), "toToken": USDT, "amount": str(amount)})
    print(json.dumps(q, indent=2)[:700])

    # 3) Optional: check allowance for whatever spender the quote names.
    print("\n=== check_allowance (token -> ??? ) ===")
    try:
        al = await twak.call("check_allowance", {
            "address": config.AGENT_WALLET, "chain": config.CHAIN, "tokenAddress": addr})
        print(json.dumps(al, indent=2)[:500])
    except Exception as exc:  # noqa: BLE001
        print(f"check_allowance error: {exc}")

    if input("\nType YES to EXECUTE the real sell and dump the raw swap result: ").strip() != "YES":
        sys.exit("aborted (quote-only).")

    # 4) Execute the swap — dump the FULL raw result.
    print("\n=== swap (SELL) RAW RESULT ===")
    r = await twak.call("swap", {
        "fromChain": config.CHAIN, "toChain": config.CHAIN,
        "fromToken": _token_ref(SYM), "toToken": USDT,
        "amount": str(amount), "slippage": str(config.SLIPPAGE_PCT)}, timeout=300)
    print(json.dumps(r, indent=2) if isinstance(r, (dict, list)) else repr(r))

    await twak.aclose()


if __name__ == "__main__":
    asyncio.run(main())
