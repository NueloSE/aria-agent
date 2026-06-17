# ARIA — Design Rules & Competition Notes

> Canonical engineering rules for this project. If code and this document
> disagree, this document wins — fix the code.

## What this project is

ARIA (Adaptive Regime Intelligence Agent) is an autonomous crypto trading agent competing in **BNB Hack: AI Trading Agent Edition** (Track 1 — Autonomous Trading Agents). It trades live on BNB Smart Chain (BSC) during a judged one-week window (June 22–28, 2026) and is scored on real PnL **subject to a maximum drawdown cap**.

**Submission deadline: June 21, 2026. On-chain registration before June 22 (mandatory). Hard deadlines. Prioritize working over perfect.**

## Official competition rules (from organizer FAQ, Telegram, 2026-06-11)

- **Tracks are pick-one.** Track 1: $24k, 5 winners. (Track 2 Strategy Skills: $6k, 3 winners — we are NOT entering it.) Plus three $2k special prizes: best use of TWAK, Agent Hub, BNB AI Agent SDK — these appear separate from track placement, so integrate all three well.
- **Timeline:** build June 3–21 · register on-chain before June 22 · live trading June 22–28 · judging June 29–July 5 · winners week of July 6.
- **Registration:** `twak compete register` (CLI) or `competition_register` (MCP) — ✅ VERIFIED working in twak v0.18.0 (probed 2026-06-12). On-chain deadline per `twak compete status`: **2026-06-25T00:00:00Z** (register before live window starts June 22 anyway). Then submit agent address + short strategy explainer on DoraHacks. Public repo + demo link/video required. Our agent wallet: `0xA935c0bE3b42385B6Cf7059979c7902AD4929B9B` (not yet registered).
- **Scoring:** ranked by **raw total return**; max-drawdown cap (~30% per the rules' example) is a **disqualification gate**, not a penalty. "Most profit without blowing up."
- **Simulated transaction costs** are applied to scoring (participants report ~1.5% per round trip — UNCONFIRMED). High trade frequency is penalized; trade rarely, with conviction.
- **Activity requirements:** minimum **1 trade per day (7 over the week)**. Must hold a non-zero in-scope balance at the start. Any hour beginning with a sub-$1 portfolio scores **0% for that hour** — keep capital deployed.
- **Eligible tokens:** a fixed official list of **149 BEP-20 tokens** on CMC. Trades outside it don't count. This list is the OUTER gate of TRADING_UNIVERSE — obtain it and commit it to the repo.
- **You fund your own agent wallet.** Whether ranking uses % return or absolute PnL is an open organizer question — fund modestly until clarified.

### Organizer rulings status (updated 2026-06-12 from Telegram)
1. ~~Perps?~~ **RESOLVED: SPOT ONLY, via the TWAK swap interface** (official admin
   ruling). No leverage in the field → compressed return distribution → our
   drawdown-disciplined design is MORE competitive. Zero design change needed.
2. ~~% return vs absolute PnL~~ **RESOLVED (admin, 2026-06-12): scoring is
   PERCENTAGE return** — start capital -> end capital, with mid-week deposits
   subtracted/adjusted ("$1 -> $2 = 100%"). Implications:
   - Wallet size doesn't matter for ranking -> fund modestly (~$100-200 is plenty)
   - Fund FULLY before the window opens; never top up mid-week (gets adjusted,
     muddies our accounting)
   - Starting capital composition: USDT (in-scope, satisfies the non-zero
     in-scope-at-start rule) + small BNB for gas (BNB is NOT in-scope)
3. **Official cost model — STILL OPEN.** Confirmed: scoring uses SIMULATED costs,
   NOT live TWAK quotes. A participant measured ~1.4% on live quotes; admins
   explicitly said don't calibrate break-even to that. Keep trade frequency low
   and mean reversion cut until the model is published; admin "asked and will
   let us know".
4. ~~compete register~~ **RESOLVED: shipped in twak v0.18.0, verified working.**
5. **CONFIRMED by admins:** ETH/USDT round-trips count as trades; the daily-trade
   rule is a qualification constraint, not a scoring lever → our USDT↔ETH
   compliance heartbeat design is exactly right.
6. **CONFIRMED (admin, 2026-06-12): TWAK swap interface is the ONLY allowed trade
   path** — exactly what `aria/execution/` does.
7. **NEW (admin, 2026-06-12): WE control start/stop — "the first trading day starts
   at the exact same time the submission time ends."** DoraHacks description being
   updated. TODO (Stage 8): add COMPETITION_START_UTC / COMPETITION_END_UTC to
   config; before start the loop runs but holds (no strategy trades); at start the
   wallet must already hold USDT (in-scope-at-start rule); at end, stop trading.
   Pin exact timestamps once the DoraHacks page is edited.

## Core concept

ARIA classifies the market regime BEFORE choosing a strategy, then routes to one of three modes:

1. **Narrative Rotation** (trending) — use CMC sector/narrative momentum to find the hottest narrative, buy its most liquid whitelisted BSC tokens
2. **Mean Reversion** (ranging) — trade blue-chip range oscillations with tight stops
3. **Capital Preservation** (high-risk/volatile) — close positions, hold stablecoins, do nothing

### Execution model: two-speed loop (LLM as judge)

ARIA runs a **decoupled two-speed loop** (the Binacci-style pattern, adapted to keep our LLM edge):

- **Fast deterministic loop** (`POLL_INTERVAL_SEC`, default 30s while holding / `POLL_INTERVAL_FLAT_SEC` 90s while flat — adaptive). No LLM. Every tick: poll quotes (ONE CMC credit, batched) → record price history → load portfolio → **manage open positions (mechanical exits: take-profit / stepped trailing / stop-loss)** → circuit breaker → run the deterministic entry gates. Exits and the breaker are *always* mechanical and never wait on the model — de-risking must be instant.
- **Cached macro read** (`MACRO_REFRESH_SEC`, default 10 min). The expensive multi-call fetch (Fear & Greed, BTC dominance, altcoin season, narratives) refreshes on a slow cadence and is cached. From it we derive a coarse, deterministic **global risk posture** (`aria/regime.py`): `risk_off` (no new entries — skip the LLM entirely), `cautious` (mean-reversion only, half size), `risk_on`/`neutral` (both plays, full size).
- **Event-driven LLM judge.** The LLM is **not** in the loop. It is called only when a deterministic gate surfaces an entry *candidate*, to **APPROVE or REJECT** that single setup on macro-regime grounds (it cannot pick a token or invent a trade; it may only trim size). This is cheaper (often zero calls in a quiet hour), more responsive (fires the moment a setup appears), and more robust (the model can only bless real gate signals, never hallucinate a position). See `aria/brain/judge_entry` + `JUDGE_SYSTEM_PROMPT`.

CMC credit note: quotes are 1 credit/poll regardless of universe size; 30s continuous exceeds the free 15k/month tier over a full week, so the live week uses adaptive cadence + (if needed) a paid CMC plan or `POLL_INTERVAL_SEC=60`.

An LLM (Claude via the Anthropic API) is the per-entry judge and logs its full reasoning chain. The deterministic gates pick the token; the LLM vetoes; the safety layer re-validates everything independently.

## ⚠️ CRITICAL: Unknown vendor APIs — do not guess

The three sponsor tools below launched in June 2026 — newer than most documentation and any prior assumptions. **Never invent or assume their APIs, function names, endpoints, or schemas.** Before writing any integration code:

1. Read the saved vendor docs in `docs/vendor/` — populated 2026-06-11: `cmc-agent-hub/NOTES.md` and `trust-wallet-agent-kit/NOTES.md` are fetched doc summaries; `bnb-ai-agent-sdk/` is the **full cloned repo** (read its README.md and ARCHITECTURE.md directly).
2. The NOTES files are a map, not gospel — if behavior is undocumented or ambiguous, write a tiny test script to probe the real API and confirm before building on it.
3. If docs you need aren't there, STOP and source them before writing code.

Guessed SDK calls are this project's #1 failure risk.

### ⚠️ Corrected vendor roles (original plan was wrong about these)

- **BNB AI Agent SDK has NO swap/DEX functionality.** It is ERC-8004 agent identity
  registration + ERC-8183 agentic commerce/escrow (Python, `pip install bnbagent`).
  ARIA uses it to register an on-chain agent identity (gas-free on BSC testnet via
  MegaFuel) — that is our "best use of BNB AI Agent SDK" special-prize angle.
- **All trade execution goes through TWAK via MCP (probed 2026-06-12, v0.18.0):**
  `twak serve --password <pw>` is an MCP server over stdio exposing real execution
  tools (`swap`, `transfer`, `validate_transaction`, `check_token_risk`,
  `get_balance`, `competition_register`, …). `aria/execution/` runs a long-lived
  `twak serve` subprocess and speaks MCP to it — no CLI output parsing. Full
  observed schemas: `docs/vendor/trust-wallet-agent-kit/observed-tools.json`.
  TWAK uses an embedded encrypted wallet unlocked by password — `.env` needs
  `TWAK_WALLET_PASSWORD`, **not** a raw `WALLET_PRIVATE_KEY`.
- **⚠️ TWAK has NO testnet support** (all 26 chains mainnet-only). Execution testing
  = quotes (free) + mock execution + **dust-size real mainnet trades ($2–5)** after
  circuit-breaker tests pass. Testnet is only used for bnbagent ERC-8004 registration.
- **CMC MCP has no literal "market regime" tool.** Regime must be SYNTHESIZED by the
  LLM from: Global Market Metrics (Fear & Greed, Altcoin Season, BTC dominance),
  Market Cap TA (trend), Derivatives Data (leverage/funding/liquidations), Macro
  Events, Trending Narratives. This is a feature — it makes the LLM's role real and
  defensible to judges, not an if/else over a vendor field.

## Tech stack

- **Python 3.11+ / FastAPI** — agent backend
- **CMC Agent Hub** (MCP server at `https://mcp.coinmarketcap.com/mcp`, auth header `X-CMC-MCP-API-KEY`) — quotes, global metrics, TA, trending narratives, derivatives, on-chain metrics, macro events
- **Anthropic API (Claude Sonnet)** — reasoning brain: regime synthesis + strategy routing
- **Trust Wallet Agent Kit (TWAK)** — wallet + ALL trade execution (`twak swap … --chain bsc`); also `twak risk` for token vetting
- **BNB AI Agent SDK** (`bnbagent`) — ERC-8004 on-chain agent identity registration only (no trading role)
- **SQLite** — trade log and decision audit trail
- **React + Tailwind** — monitoring dashboard (in /dashboard)

## Architecture

- `aria/signals/` — CMC client only. No trading logic.
- `aria/brain/` — LLM loop. Input: signals + state. Output: a validated Decision (schema below).
- `aria/strategies/` — one module per mode. Strategies propose trades; they never execute.
- `aria/safety/` — circuit breakers. VETO POWER OVER EVERYTHING, including the LLM.
- `aria/execution/` — the only module allowed to sign/send transactions.
- `aria/state/` — portfolio state + SQLite logging.

## The Decision schema (contract between brain → safety → execution)

Every LLM output MUST validate against this Pydantic model before anything acts on it:

```python
class Decision(BaseModel):
    cycle_id: str                    # uuid for this decision cycle
    timestamp: datetime
    regime: Literal["trending", "ranging", "high_risk"]
    mode: Literal["narrative_rotation", "mean_reversion", "preservation"]
    action: Literal["buy", "sell", "close_all", "hold"]
    token_symbol: str | None         # must be in TRADING_UNIVERSE; None for hold/close_all
    size_pct: float                  # % of portfolio, 0.0–MAX_POSITION_PCT; 0 for hold
    stop_loss_pct: float | None      # required for buy actions
    confidence: float                # 0.0–1.0; below CONFIDENCE_FLOOR → treat as hold
    reasoning: str                   # plain-English explanation, logged verbatim
```

Malformed or non-validating LLM output → treat as `hold`, log the error, continue. Never crash the loop on bad LLM output.

## Trading universe (whitelist — the agent may ONLY trade these)

Defined in `aria/config.py` as `TRADING_UNIVERSE`. **Outer gate: the official 149
eligible BEP-20 token list — trades outside it score nothing. Obtain the list, commit
it to the repo as data, and intersect every gate below with it.** Starting set (human
may revise after checking BSC liquidity):

- **⚠️ BNB/WBNB/BTCB are NOT on the eligible list** (verified against the official
  149-token list, `aria/data/eligible_tokens.json`). No BNB or BTC variants at all.
  The wallet still needs native BNB for GAS, but it can't be traded for score.
- **Blue chips set:** ETH, CAKE, LINK (eligible-list members with deep BSC liquidity)
- **Stables / preservation set:** USDT, USDC
- **Compliance trade pair:** USDT↔ETH (NOT WBNB — ineligible; and avoid stable↔stable
  in case organizers don't count it as a "trade")
- **Narrative set:** populated dynamically from CMC narrative momentum BUT filtered to tokens that (a) are in the top N of their narrative by market cap, (b) exceed a minimum liquidity threshold from CMC liquidity signals, and (c) have a verified PancakeSwap pool. The filter lives in `aria/strategies/narrative_rotation.py` and its thresholds in config.

Any token not passing these gates is untradeable, regardless of what the LLM says.

## Strategy parameters (starting values in `aria/config.py` — tune during testnet)

```python
CYCLE_INTERVAL_MIN = 30          # decision loop frequency (reasoning cadence ≠ trading cadence — trade rarely)
MAX_DRAWDOWN_PCT = 30.0          # official DQ gate per rules' example (~30%)
HALT_DRAWDOWN_PCT = 20.0         # our circuit breaker fires well before the gate
MAX_POSITION_PCT = 15.0          # max % of portfolio in one trade
CONFIDENCE_FLOOR = 0.6           # LLM judge confidence below this → reject entry
MAX_CONCURRENT_POSITIONS = 4     # cap on simultaneously open positions

# Two-speed loop cadence (see "Execution model")
POLL_INTERVAL_SEC = 30           # fast loop while holding (tight exit management)
POLL_INTERVAL_FLAT_SEC = 90      # fast loop while flat (entry signals move slowly)
MACRO_REFRESH_SEC = 600          # cached macro/regime read cadence (10 min)
# CYCLE_INTERVAL_MIN retained only for back-compat (the old single-cadence knob)

# Rule compliance (mandatory — lives in safety/execution, NOT under LLM control)
MIN_TRADES_PER_DAY = 1           # rules: 1 trade/day, 7 over the week
COMPLIANCE_TRADE_HOUR = 20       # if no strategy trade by this hour (UTC), execute minimal in-scope swap
COMPLIANCE_TRADE_SIZE_PCT = 0.5  # tiny — exists only to satisfy the rule (size vs tx-cost: confirm cost model first)
MIN_DEPLOYED_USD = 5.0           # any hour starting under $1 scores 0% — never go fully idle

# Mean reversion — ⚠️ LIKELY CUT. If simulated tx costs are ~1.5% per round trip
# (unconfirmed), a 3% entry band + 2.5% stop has no edge after costs. Build this
# mode LAST, and only if the official cost model makes it viable. A two-mode agent
# (narrative rotation + preservation) that works beats three modes with one leaking.
MR_LOOKBACK_HOURS = 48           # range detection window
MR_ENTRY_BAND_PCT = 3.0          # buy within 3% of range low / sell within 3% of high
MR_STOP_LOSS_PCT = 2.5

# Narrative rotation
NR_TOP_TOKENS_PER_NARRATIVE = 3
NR_MIN_LIQUIDITY = TBD           # set after seeing CMC liquidity signal units
NR_STOP_LOSS_PCT = 6.0
NR_MAX_NARRATIVE_ALLOCATION = 40.0  # max % of portfolio in one narrative

# Preservation
PRESERVATION_TARGET = "USDT"
```

These are starting points, not gospel — tune on testnet, but always via config, never hardcoded in strategy logic.

## Live-window failure behavior (judged week — June 22–28)

- **CMC API unreachable:** skip the cycle, log it, retry next cycle. After 3 consecutive failures → enter preservation mode (close to stables) until signals return.
- **Anthropic API unreachable:** same policy as above. No signals or no brain = no trading.
- **Transaction reverts/fails:** log, do NOT auto-retry the same trade more than once. Recompute on next cycle with fresh state.
- **Process crash:** systemd/supervisor restarts the agent; on startup it MUST reconcile actual on-chain balances with its database before trading (never trust stale local state).
- **Drawdown approaches HALT_DRAWDOWN_PCT (20%, well inside the 30% DQ gate):** close everything, halt strategy trading, alert the human. Require manual restart. ⚠️ Even while halted, the daily compliance trade MUST still execute — going silent for a day violates the 1-trade/day rule.
- **Preservation mode** holds stables but must still (a) execute the daily compliance trade and (b) keep ≥ MIN_DEPLOYED_USD in-scope — a sub-$1 portfolio at the top of any hour scores 0% for that hour.

## Hard rules — never violate

1. **Safety layer overrides the LLM.** No exceptions.
2. **Never commit secrets.** All keys in `.env` (git-ignored). If a private key or API key is about to enter a tracked file, stop and refuse.
3. **Safest-path first.** TWAK has no testnet, so the ladder is: mock execution → quotes only (`get_swap_quote`, free) → dust-size mainnet trades ($2–5) → live capital. Each rung requires the previous one passing, and dust trades require circuit-breaker tests green (rule #7). BSC testnet is used only for bnbagent ERC-8004 registration.
4. **Whitelist only.** No trades outside TRADING_UNIVERSE gates.
5. **Default to inaction.** Ambiguous signals, low confidence, or any validation failure → hold. Log it anyway.
6. **Every decision logged** — including holds — with timestamp, signals snapshot, full LLM reasoning, and outcome.
7. **Circuit breakers must have unit tests** before any mainnet run.

## Code style

- Type hints everywhere; Pydantic models for all cross-module data
- Small modules, single responsibility
- Fail loudly in dev, fail safe in production (live-window errors must never leave positions unmanaged)
- Async for API calls, simple sync elsewhere

## Priority order if time runs short

1. End-to-end loop on testnet (signals → decision → safety → execute → log)
2. Circuit breaker tests passing
3. 24h+ unattended testnet run
4. Dashboard
5. Demo video + submission polish

Cut dashboard polish before anything else. Never cut safety or logging.

## Open questions

- ~~Exact drawdown cap %~~ → RESOLVED: ~30% DQ gate (rules' example); we halt at 20%
- Wallet funding amount for the live window — wait for the % vs absolute PnL ruling before deciding
- Obtain the official 149-token eligible list and commit it to the repo
- CMC Agent Hub rate limits (discover during integration, then record in docs/vendor/cmc-agent-hub/NOTES.md)
- Final trading universe after liquidity check
- Watch Telegram for the four pending organizer rulings (perps, PnL basis, cost model, compete-register docs)
- Get TWAK credentials (portal.trustwallet.com → Access ID + HMAC Secret) and CMC API key (pro.coinmarketcap.com)
