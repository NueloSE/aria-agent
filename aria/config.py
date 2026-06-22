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
# Real figure confirmed by organizers (2026-06-20): 0.077%/leg, ~0.15% round-trip
# (waived from 0.7% for the trading week). Cost is now ~10x lower than our earlier
# conservative placeholder, so small frequent wins are genuinely profitable.
SIM_COST_PCT_PER_LEG = _env_float("SIM_COST_PCT_PER_LEG", 0.077)

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
MAX_CONCURRENT_POSITIONS = int(_env_float("MAX_CONCURRENT_POSITIONS", 6))  # cap open positions (raised 4->6: cost is cheap, deploy more)
CONFIDENCE_FLOOR = 0.6

# --- Rule compliance (mandatory; enforced by safety/scheduler, never the LLM) ---
MIN_TRADES_PER_DAY = 1
COMPLIANCE_TRADE_HOUR_UTC = 20      # if no trade by this hour, force minimal swap
COMPLIANCE_TRADE_SIZE_PCT = 0.5
MIN_DEPLOYED_USD = 1.0              # lowered: wallet starts at ~$5, need headroom

# --- Fee-aware min-edge gate (the discipline that prevents cost-bleed) ---
# A buy's take-profit target must clear the round-trip cost by this multiple,
# else it's a guaranteed loser and the safety layer vetoes it.
def round_trip_cost_pct() -> float:
    return 2.0 * SIM_COST_PCT_PER_LEG          # both legs of the simulated cost
MIN_EDGE_MULTIPLE = _env_float("MIN_EDGE_MULTIPLE", 1.5)   # target >= 1.5x cost
# After exiting a token, don't re-buy it for this long — prevents take-profit/stop
# → immediate re-entry churn that bleeds to costs.
REENTRY_COOLDOWN_MIN = _env_float("REENTRY_COOLDOWN_MIN", 120.0)
# After the LLM judge REJECTS a candidate, don't re-judge that same token for this long
# — stops paying for the same reject every tick, and lets the gate fall through to the
# next-best candidate. Short (15 min) so a setup that genuinely turns isn't missed.
REJECT_COOLDOWN_MIN = _env_float("REJECT_COOLDOWN_MIN", 15.0)

# --- Exit management: stepped trailing stop + take-profit (lock winners, cut losers) ---
TRAIL_TRIGGER_PCT = _env_float("TRAIL_TRIGGER_PCT", 1.5)   # arm trailing once gain >= this (lowered 2.5->1.5: cheap costs let us lock smaller wins)
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
MR_RECLAIM_24H_PCT = _env_float("MR_RECLAIM_24H_PCT", 0.5)     # 24h change >= this (turning back up over the day)
MR_RECLAIM_1H_TURN_PCT = _env_float("MR_RECLAIM_1H_TURN_PCT", 0.3)  # OR 1h change >= this: catches the EARLY turn before 24h flips green (more setups when the market stabilizes)
MR_RECLAIM_1H_PCT = _env_float("MR_RECLAIM_1H_PCT", -1.5)      # 1h floor: reject if dumping harder than this THIS hour (anti dead-cat)
MR_MAX_7D_RUN_PCT = _env_float("MR_MAX_7D_RUN_PCT", 12.0)      # skip if 7d > this (already bounced — catch it EARLY; tightened 15->12)
MR_MIN_VOL_CHANGE_PCT = _env_float("MR_MIN_VOL_CHANGE_PCT", -25.0)  # 24h volume change >= this: reclaim on returning (not collapsing) volume
MR_MIN_LIQUIDITY_USD = 5_000_000   # only deep, safe names for counter-trend
# Quality gates (added 2026-06-18 after the IP loss): mean-reversion targets names that
# are temporarily oversold, NOT ones in a structural collapse. A token down catastrophically
# over the year/quarter is a dying falling-knife, not a reversion candidate.
MR_MAX_RANK = int(_env_float("MR_MAX_RANK", 250))            # skip deep micro-caps (CMC rank worse than this)
MR_MAX_1Y_DECLINE_PCT = _env_float("MR_MAX_1Y_DECLINE_PCT", -85.0)    # skip structurally broken (1y <= this)
MR_MAX_90D_DECLINE_PCT = _env_float("MR_MAX_90D_DECLINE_PCT", -70.0)  # fallback guard when 1y is absent (newer tokens)
MR_STOP_LOSS_PCT = 5.0
MR_TARGET_PCT = _env_float("MR_TARGET_PCT", 4.0)  # default snap-to-mean target (lowered 7->4: real cost ~0.15%, exit the bounce sooner)
MR_SIZE_PCT = 10.0
# Per-candidate TECHNICAL confirmation (get_crypto_technical_analysis, 1 credit on the
# single top candidate only). Real RSI confirms genuine oversold (not just "down"), and
# Fibonacci levels give structure-aware targets/stops. Organizers explicitly reward
# support/resistance use. Fail-safe: if the call fails, entry proceeds without it.
MR_CONFIRM_ENABLED = os.getenv("MR_CONFIRM_ENABLED", "true").lower() == "true"
MR_RSI_MAX = _env_float("MR_RSI_MAX", 48.0)        # enter only if RSI-14 <= this (oversold-leaning)
MR_FIB_TARGET_MIN_PCT = _env_float("MR_FIB_TARGET_MIN_PCT", 1.5)   # nearest resistance >= this is tradeable (lowered 3.5->1.5: cost is ~0.15%, small bounces profit)
MR_FIB_TARGET_MAX_PCT = _env_float("MR_FIB_TARGET_MAX_PCT", 20.0)  # ignore implausibly far fib targets
MR_FIB_STOP_MIN_PCT = _env_float("MR_FIB_STOP_MIN_PCT", 3.0)       # fib-derived stop must be at least this
MR_FIB_STOP_MAX_PCT = _env_float("MR_FIB_STOP_MAX_PCT", 8.0)       # ...and at most this
# Scoring weights — a real bottom is washed out AND reclaiming on rising volume.
MR_W_WASHOUT = _env_float("MR_W_WASHOUT", 1.0)       # depth of the 30d washout
MR_W_RECLAIM_24H = _env_float("MR_W_RECLAIM_24H", 1.0)   # 24h turn (capped)
MR_W_RECLAIM_1H = _env_float("MR_W_RECLAIM_1H", 0.5)     # 1h confirmation (capped)
MR_W_VOLUME = _env_float("MR_W_VOLUME", 0.15)            # rising 24h volume (capped)
MR_W_CHASE_PENALTY = _env_float("MR_W_CHASE_PENALTY", 0.5)  # penalize already-recovered 7d

# --- Global risk posture (coarse macro guard, refreshed every MACRO_REFRESH_SEC) ---
# A cheap deterministic gate over the cached macro read that sets a GLOBAL stance the
# fast loop respects BEFORE it ever calls the LLM. The LLM is the nuanced per-trade
# judge; this is the blunt "is the whole market too dangerous to add risk" switch, so
# we don't even spend an LLM call when macro is clearly risk-off.
POSTURE_EXTREME_FEAR = _env_float("POSTURE_EXTREME_FEAR", 15.0)   # F&G <= this -> no new entries
POSTURE_CRASH_7D_PCT = _env_float("POSTURE_CRASH_7D_PCT", -15.0)  # total mcap 7d <= this -> no new entries
POSTURE_CAUTION_FEAR = _env_float("POSTURE_CAUTION_FEAR", 25.0)   # F&G <= this -> half size, MR only
POSTURE_SOFT_7D_PCT = _env_float("POSTURE_SOFT_7D_PCT", -8.0)     # total mcap 7d <= this -> half size, MR only

# --- Strategy: breakout / momentum (covers RECOVERING & trending markets that the
# counter-trend oversold-reclaim play misses — more quality setups across the cycle) ---
# Buy a quality token that is breaking UP on real volume but isn't overextended. Cheap
# quote-field gates find the candidate; per-candidate TA then confirms (RSI not overbought,
# Fibonacci extension for the target). Reuses the MR quality gates (rank / not-dying).
BO_ENABLED = os.getenv("BO_ENABLED", "true").lower() == "true"
BO_MIN_24H_PCT = _env_float("BO_MIN_24H_PCT", 4.0)      # up at least this on the day (clearly moving)
BO_MIN_1H_PCT = _env_float("BO_MIN_1H_PCT", 0.0)        # still up THIS hour (not already reversing)
BO_MIN_VOL_CHANGE_PCT = _env_float("BO_MIN_VOL_CHANGE_PCT", 25.0)  # volume up >= this (real participation)
BO_MIN_7D_PCT = _env_float("BO_MIN_7D_PCT", -10.0)     # 7d base forming, not in freefall
BO_MAX_7D_PCT = _env_float("BO_MAX_7D_PCT", 40.0)      # not already ripped (no chasing)
BO_RSI_MAX = _env_float("BO_RSI_MAX", 70.0)            # reject if RSI-14 overbought (no room to run)
BO_MIN_LIQUIDITY_USD = 5_000_000
BO_TARGET_PCT = _env_float("BO_TARGET_PCT", 6.0)       # default target if no fib extension fits (lowered 10->6: cheap costs)
BO_STOP_LOSS_PCT = _env_float("BO_STOP_LOSS_PCT", 5.0)
BO_SIZE_PCT = _env_float("BO_SIZE_PCT", 10.0)

# --- Strategy: preservation ---
PRESERVATION_TARGET = "USDT"

# --- Signal layer ---
# live = real MCP calls (1 credit each, ~6/cycle); fixtures = offline Stage-1 captures
SIGNALS_MODE = os.getenv("SIGNALS_MODE", "live" if os.getenv("CMC_MCP_API_KEY") else "fixtures")
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
SIGNAL_TIMEOUT_S = 60
SIGNAL_MAX_CONSECUTIVE_FAILURES = int(_env_float("SIGNAL_MAX_CONSECUTIVE_FAILURES", 10))
# Raised 3 -> 10 (2026-06-18): with per-call retry-backoff already absorbing single
# blips, a brief signal gap (a laptop sleeping, a transient outage) should NOT liquidate
# stop-protected positions. ~10 consecutive failed ticks (several minutes blind) still
# de-risks to stables on a genuinely sustained outage.
# Per-call resilience: a transient transport blip or CMC 5xx is retried in-place with
# backoff so it never counts toward the consecutive-failure tally. A sustained outage
# (e.g. internet down) still exhausts retries -> the tick fails -> preservation kicks in.
SIGNAL_RETRY_ATTEMPTS = int(_env_float("SIGNAL_RETRY_ATTEMPTS", 3))
SIGNAL_RETRY_BACKOFF_S = _env_float("SIGNAL_RETRY_BACKOFF_S", 0.5)

# --- State ---
DB_PATH = Path(os.getenv("ARIA_DB", ROOT / "aria.sqlite3"))

# --- Dashboard ---
# When the API is exposed publicly (e.g. the Vercel demo URL proxies to it), the
# operator POST endpoints (window / override / clear-halt) must be inert. Set
# DASHBOARD_READONLY=true on the public host; the agent itself is unaffected.
DASHBOARD_READONLY = os.getenv("DASHBOARD_READONLY", "false").lower() == "true"

# --- Trading universe ---
# Outer gate: official 149-token eligible list (trades outside it score nothing).
_eligible = json.loads((ROOT / "aria" / "data" / "eligible_tokens.json").read_text())
ELIGIBLE_SYMBOLS: frozenset[str] = frozenset(_eligible["symbols"])

# Tracked universe — 30 liquid eligible large/mid caps we price + scan every cycle
# (candidates for both narrative rotation and mean-reversion). All on the official
# eligible list; BNB/WBNB/BTC/BTCB are NOT eligible so they're absent by design.
BLUE_CHIPS = (
    "ETH", "XRP", "TRX", "DOGE", "ADA", "LINK", "BCH", "TON", "LTC", "AVAX",
    "SHIB", "DOT", "UNI", "ETC", "AAVE", "ATOM", "INJ", "FET", "CAKE",
    "ZEC", "LDO", "PENDLE", "AXS", "TWT", "COMP", "APE", "SNX", "KAVA", "SUSHI",
    "ZRO", "STG", "RAY", "BAT", "1INCH", "YFI", "ZIL", "DEXE", "ACH", "AXL",
    "PLUME", "ASTER", "LUNC", "BTT", "SFP", "FLOKI", "BONK", "PENGU", "WLFI", "IP",
)
STABLES = ("USDT", "USDC")

# Verified BSC-swappable allowlist — ONLY these tokens have a confirmed Binance-Peg
# contract + PancakeSwap liquidity (mirrors _BSC_CONTRACTS in aria/execution). The
# entry gate is constrained to this set so it never proposes a token that fails at
# swap time (e.g. RAY is Solana-native, ZEC/ZRO have no reliable BSC route). Keep in
# sync with aria/execution/__init__.py:_BSC_CONTRACTS.
TRADEABLE_SYMBOLS: frozenset[str] = frozenset({
    "ETH", "LTC", "XRP", "ADA", "DOGE", "DOT", "LINK", "ATOM",
    "UNI", "ETC", "BCH", "SHIB", "CAKE", "AVAX", "AAVE", "BTT",
})
