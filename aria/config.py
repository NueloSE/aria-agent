"""ARIA configuration. All tunables live here, loaded from env where secret/deployment-
specific. Strategy logic must never hardcode these values."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


# --- Identity / secrets ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CMC_MCP_API_KEY = os.getenv("CMC_MCP_API_KEY", "")
TWAK_WALLET_PASSWORD = os.getenv("TWAK_WALLET_PASSWORD", "")

# --- LLM brain ---
BRAIN_MODE = os.getenv("BRAIN_MODE", "mock")            # mock | live
BRAIN_MODEL = os.getenv("BRAIN_MODEL", "claude-haiku-4-5")

# --- Chain / execution ---
# TWAK has no testnet (probed 2026-06-12). Real swaps require ALL THREE:
# EXECUTION_MODE=live AND NETWORK=mainnet AND not --dry-run.
#   stub  = skip fills (offline dev / dry-run soak)
#   paper = simulate fills at market price + simulated cost (no funds, no chain)
#   live  = real swaps via twak serve
NETWORK = os.getenv("NETWORK", "testnet")
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "stub")   # stub | paper | live
CHAIN = "bsc"
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.bnbchain.org")
AGENT_WALLET = "0xA935c0bE3b42385B6Cf7059979c7902AD4929B9B"
SLIPPAGE_PCT = _env_float("SLIPPAGE_PCT", 1.0)          # twak default; max 50
MAX_PRICE_IMPACT_PCT = _env_float("MAX_PRICE_IMPACT_PCT", 3.0)  # abort swap above this

# --- Paper trading (forward simulation; no funds, no chain) ---
PAPER_START_USD = _env_float("PAPER_START_USD", 100.0)
# The competition applies SIMULATED costs at market price (admins: don't calibrate
# to live TWAK quotes). Mirror that: cost per leg. ~0.75%/leg ≈ 1.5% round trip —
# a placeholder until organizers publish the official model. One env var to retune.
SIM_COST_PCT_PER_LEG = _env_float("SIM_COST_PCT_PER_LEG", 0.75)

# --- Loop ---
CYCLE_INTERVAL_MIN = _env_float("CYCLE_INTERVAL_MIN", 30.0)

# --- Risk (competition rules: ~30% max drawdown = disqualification gate) ---
MAX_DRAWDOWN_PCT = _env_float("MAX_DRAWDOWN_PCT", 30.0)
HALT_DRAWDOWN_PCT = _env_float("HALT_DRAWDOWN_PCT", 20.0)
MAX_POSITION_PCT = _env_float("MAX_POSITION_PCT", 15.0)
CONFIDENCE_FLOOR = 0.6

# --- Rule compliance (mandatory; enforced by safety/scheduler, never the LLM) ---
MIN_TRADES_PER_DAY = 1
COMPLIANCE_TRADE_HOUR_UTC = 20      # if no trade by this hour, force minimal swap
COMPLIANCE_TRADE_SIZE_PCT = 0.5
MIN_DEPLOYED_USD = 5.0              # sub-$1 portfolio at top of hour scores 0%

# --- Strategy: narrative rotation ---
NR_TOP_TOKENS_PER_NARRATIVE = 3
NR_MIN_LIQUIDITY_USD = 1_000_000    # provisional — tune after observing CMC data
NR_STOP_LOSS_PCT = 6.0
NR_MAX_NARRATIVE_ALLOCATION = 40.0

# --- Strategy: mean reversion (LIKELY CUT — see docs/DESIGN.md; built last if ever) ---
MR_ENABLED = False
MR_LOOKBACK_HOURS = 48
MR_ENTRY_BAND_PCT = 3.0
MR_STOP_LOSS_PCT = 2.5

# --- Strategy: preservation ---
PRESERVATION_TARGET = "USDT"

# --- Signal layer ---
# live = real MCP calls (1 credit each, ~6/cycle); fixtures = offline Stage-1 captures
SIGNALS_MODE = os.getenv("SIGNALS_MODE", "live" if os.getenv("CMC_MCP_API_KEY") else "fixtures")
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
SIGNAL_TIMEOUT_S = 60
SIGNAL_MAX_CONSECUTIVE_FAILURES = 3  # then force preservation until signals return

# --- State ---
DB_PATH = Path(os.getenv("ARIA_DB", ROOT / "aria.sqlite3"))

# --- Trading universe ---
# Outer gate: official 149-token eligible list (trades outside it score nothing).
_eligible = json.loads((ROOT / "aria" / "data" / "eligible_tokens.json").read_text())
ELIGIBLE_SYMBOLS: frozenset[str] = frozenset(_eligible["symbols"])

# Blue chips / preservation set we actively use (must be subsets of eligible list)
BLUE_CHIPS = ("ETH", "CAKE", "LINK")    # note: WBNB/BTCB are NOT on the eligible list
STABLES = ("USDT", "USDC")
