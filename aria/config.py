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

# --- Loop (decoupled cadence: fast deterministic loop + event-driven LLM) ---
# The fast loop polls quotes, manages exits, and runs the deterministic entry gates
# every POLL_INTERVAL_SEC. The LLM is NOT in this loop — it is called only when a
# gate surfaces an entry candidate (the "LLM as judge" model). Exits (take-profit /
# trailing / stop / breaker) are always mechanical and never wait on the model.
#
# CMC credit note: quotes = 1 credit per poll (one batched call, any universe size).
# At 30s continuous that is ~2880 credits/day — over the free 15k/month tier for a
# full week. Two mitigations: (1) adaptive cadence — poll FLAT markets slower (entry
# signals don't move in 30s), only poll fast while holding (exits need it); (2) for
# the live competition week, a paid CMC plan or POLL_INTERVAL_SEC=60 keeps it in budget.
POLL_INTERVAL_SEC = _env_float("POLL_INTERVAL_SEC", 30.0)        # while holding (tight exit mgmt)
POLL_INTERVAL_FLAT_SEC = _env_float("POLL_INTERVAL_FLAT_SEC", 90.0)  # while flat (entries are slow)
# Macro/regime read (F&G, BTC dominance, altseason, narratives) is the expensive
# multi-call fetch — refresh it on this slower cadence and cache the posture between.
MACRO_REFRESH_SEC = _env_float("MACRO_REFRESH_SEC", 600.0)        # 10 min, like Binacci's macro gate
# Back-compat: the old single-cadence knob. Unused by the fast loop; kept so any
# external caller/import doesn't break.
CYCLE_INTERVAL_MIN = _env_float("CYCLE_INTERVAL_MIN", 15.0)

# --- Risk (competition rules: ~30% max drawdown = disqualification gate) ---
MAX_DRAWDOWN_PCT = _env_float("MAX_DRAWDOWN_PCT", 30.0)
HALT_DRAWDOWN_PCT = _env_float("HALT_DRAWDOWN_PCT", 20.0)
MAX_POSITION_PCT = _env_float("MAX_POSITION_PCT", 15.0)
MAX_CONCURRENT_POSITIONS = int(_env_float("MAX_CONCURRENT_POSITIONS", 4))  # cap open positions
CONFIDENCE_FLOOR = 0.6

# --- Rule compliance (mandatory; enforced by safety/scheduler, never the LLM) ---
MIN_TRADES_PER_DAY = 1
COMPLIANCE_TRADE_HOUR_UTC = 20      # if no trade by this hour, force minimal swap
COMPLIANCE_TRADE_SIZE_PCT = 0.5
MIN_DEPLOYED_USD = 5.0              # sub-$1 portfolio at top of hour scores 0%

# --- Fee-aware min-edge gate (the discipline that prevents cost-bleed) ---
# A buy's take-profit target must clear the round-trip cost by this multiple,
# else it's a guaranteed loser and the safety layer vetoes it.
def round_trip_cost_pct() -> float:
    return 2.0 * SIM_COST_PCT_PER_LEG          # both legs of the simulated cost
MIN_EDGE_MULTIPLE = _env_float("MIN_EDGE_MULTIPLE", 1.5)   # target >= 1.5x cost
# After exiting a token, don't re-buy it for this long — prevents take-profit/stop
# → immediate re-entry churn that bleeds to costs.
REENTRY_COOLDOWN_MIN = _env_float("REENTRY_COOLDOWN_MIN", 120.0)

# --- Exit management: stepped trailing stop + take-profit (lock winners, cut losers) ---
TRAIL_TRIGGER_PCT = _env_float("TRAIL_TRIGGER_PCT", 2.5)   # arm trailing once gain >= this
TRAIL_INITIAL_SL_PCT = _env_float("TRAIL_INITIAL_SL_PCT", 1.0)  # lock this gain when armed
TRAIL_STEP_PCT = _env_float("TRAIL_STEP_PCT", 0.5)         # raise stop per step of further gain

# --- Strategy: narrative rotation (trending) ---
NR_TOP_TOKENS_PER_NARRATIVE = 3
NR_MIN_LIQUIDITY_USD = 1_000_000    # provisional — tune after observing CMC data
NR_STOP_LOSS_PCT = 6.0
NR_TARGET_PCT = 15.0   # backstop cap; the trailing stop is the primary exit so winners run
NR_MAX_NARRATIVE_ALLOCATION = 40.0

# --- Strategy: counter-trend mean reversion (oversold reclaim — works in ANY regime) ---
# Buy washed-out eligible blue chips that are TURNING BACK UP. Calibration (fixed
# 2026-06-16 after the 7d-washed gate filtered 0/30 in a recovering market): the
# real oversold signal is the 30d washout; the reclaim is "turning up now" (24h).
# A hard "still down on 7d" gate is redundant-and-stricter than 30d AND contradicts
# the reclaim, so it's dropped. An anti-chase guard skips names that already ripped.
MR_ENABLED = True
MR_STRETCH_30D_PCT = _env_float("MR_STRETCH_30D_PCT", -15.0)   # 30d change <= this (washed out on the month)
MR_RECLAIM_24H_PCT = _env_float("MR_RECLAIM_24H_PCT", 0.5)     # 24h change >= this (turning back up)
MR_MAX_7D_RUN_PCT = _env_float("MR_MAX_7D_RUN_PCT", 15.0)      # skip if 7d > this (already bounced — catch it EARLY)
MR_MIN_LIQUIDITY_USD = 5_000_000   # only deep, safe names for counter-trend
MR_STOP_LOSS_PCT = 5.0
MR_TARGET_PCT = 7.0                # snap-to-mean target; clears the fee gate (>2.25%)
MR_SIZE_PCT = 10.0

# --- Global risk posture (coarse macro guard, refreshed every MACRO_REFRESH_SEC) ---
# A cheap deterministic gate over the cached macro read that sets a GLOBAL stance the
# fast loop respects BEFORE it ever calls the LLM. The LLM is the nuanced per-trade
# judge; this is the blunt "is the whole market too dangerous to add risk" switch, so
# we don't even spend an LLM call when macro is clearly risk-off.
POSTURE_EXTREME_FEAR = _env_float("POSTURE_EXTREME_FEAR", 15.0)   # F&G <= this -> no new entries
POSTURE_CRASH_7D_PCT = _env_float("POSTURE_CRASH_7D_PCT", -15.0)  # total mcap 7d <= this -> no new entries
POSTURE_CAUTION_FEAR = _env_float("POSTURE_CAUTION_FEAR", 25.0)   # F&G <= this -> half size, MR only
POSTURE_SOFT_7D_PCT = _env_float("POSTURE_SOFT_7D_PCT", -8.0)     # total mcap 7d <= this -> half size, MR only

# --- Strategy: preservation ---
PRESERVATION_TARGET = "USDT"

# --- Signal layer ---
# live = real MCP calls (1 credit each, ~6/cycle); fixtures = offline Stage-1 captures
SIGNALS_MODE = os.getenv("SIGNALS_MODE", "live" if os.getenv("CMC_MCP_API_KEY") else "fixtures")
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
SIGNAL_TIMEOUT_S = 60
SIGNAL_MAX_CONSECUTIVE_FAILURES = 3  # then force preservation until signals return
# Per-call resilience: a transient transport blip or CMC 5xx is retried in-place with
# backoff so it never counts toward the consecutive-failure tally. A sustained outage
# (e.g. internet down) still exhausts retries -> the tick fails -> preservation kicks in.
SIGNAL_RETRY_ATTEMPTS = int(_env_float("SIGNAL_RETRY_ATTEMPTS", 3))
SIGNAL_RETRY_BACKOFF_S = _env_float("SIGNAL_RETRY_BACKOFF_S", 0.5)

# --- State ---
DB_PATH = Path(os.getenv("ARIA_DB", ROOT / "aria.sqlite3"))

# --- Trading universe ---
# Outer gate: official 149-token eligible list (trades outside it score nothing).
_eligible = json.loads((ROOT / "aria" / "data" / "eligible_tokens.json").read_text())
ELIGIBLE_SYMBOLS: frozenset[str] = frozenset(_eligible["symbols"])

# Tracked universe — 30 liquid eligible large/mid caps we price + scan every cycle
# (candidates for both narrative rotation and mean-reversion). All on the official
# eligible list; BNB/WBNB/BTC/BTCB are NOT eligible so they're absent by design.
BLUE_CHIPS = (
    "ETH", "XRP", "TRX", "DOGE", "ADA", "LINK", "BCH", "TON", "LTC", "AVAX",
    "SHIB", "DOT", "UNI", "ETC", "AAVE", "ATOM", "FIL", "INJ", "FET", "CAKE",
    "ZEC", "LDO", "PENDLE", "AXS", "TWT", "COMP", "APE", "SNX", "KAVA", "SUSHI",
    "ZRO", "STG", "RAY", "BAT", "1INCH", "YFI", "ZIL", "DEXE", "ACH", "AXL",
    "PLUME", "ASTER", "LUNC", "BTT", "SFP", "FLOKI", "BONK", "PENGU", "WLFI", "IP",
)
STABLES = ("USDT", "USDC")
