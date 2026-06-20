# ARIA — Adaptive Regime Intelligence Agent

> An autonomous AI trading agent that **reads the market's regime first — then decides how to play it.**

Built for **BNB Hack: AI Trading Agent Edition** (June 2026) — Track 1: Autonomous Trading Agents.
Organized by BNB Chain × CoinMarketCap × Trust Wallet.

---

## 🧠 What is ARIA?

Most trading agents run one fixed strategy — a momentum bot becomes a loss engine the moment
the market ranges. ARIA is different: it reads the **market regime** from live signals before
every decision, derives a **risk posture**, and runs the strategy built for that regime — and
it treats *not trading* as a position.

Crucially, ARIA uses its LLM as a **judge, not an oracle.** Deterministic strategy gates *find*
real setups from CoinMarketCap data; the LLM (Claude) only **approves, rejects, or sizes** them
against the macro picture. The model can never invent a trade — only bless one the math already
found, or veto it. The safety layer then re-validates everything before a swap ever fires.

```
CMC Agent Hub ─▶ Regime & Posture ─▶ Strategy Gates ─▶ TA Confirmation ─▶ LLM Judge ─▶ Safety ─▶ TWAK swap (BNB Chain)
   (signals)        (risk stance)      (find candidate)   (RSI + Fib)      (approve?)   (veto)      (execute)
                                                │
                          Mechanical exits + drawdown breaker run every cycle (no LLM)
```

ARIA runs a **two-speed loop**: a fast deterministic loop (~30–90s) polls prices, manages
exits, and scans the strategy gates; the **LLM is event-driven** — invoked only when a real
candidate needs judgment. Responsive and cheap, with the model's nuance exactly where it adds value.

## ⚡ The Strategies — coverage across the whole cycle

| Strategy | Fires when… | Logic |
|---|---|---|
| 🔵 **Oversold reclaim** (mean-reversion) | fearful / post-decline | buy washed-out, quality blue chips turning back up on returning volume |
| 🟢 **Breakout / momentum** | recovering / trending | buy quality tokens breaking up on real volume, not overextended |
| 🟡 **Narrative rotation** | a hot sector has momentum | buy the strongest trending CMC narrative's most liquid eligible token |
| 🔴 **Capital preservation** | no edge | sit in stablecoins — surviving the week is most of winning it |

Every candidate then passes a **per-token technical confirmation** via the CMC Agent Hub's
analysis tool: **RSI** gates the entry (genuine oversold for reclaims / not-overbought for
breakouts), and **Fibonacci levels + pivots** set a structure-aware take-profit (nearest
resistance) and stop (below support) — directly applying the support/resistance the
competition encourages. A coarse **risk posture** (`risk-on` / `neutral` / `cautious` /
`risk-off`) from the macro read decides how aggressively, or whether, to trade at all.

## 🛡️ Safety First — the rule engine outranks the model

Track 1 is ranked on **% return with a ~30% max-drawdown disqualification gate.** ARIA treats
that as a first-class constraint, with a mechanical risk layer that runs every cycle (no LLM):

- **Mechanical exits** — take-profit at the Fibonacci target, a **stepped trailing stop** that
  walks into profit and locks winners, and a hard stop-loss. De-risking never waits on the model.
- **Hard circuit breaker** — at 20% drawdown (well inside the 30% gate) ARIA flattens everything,
  halts, and requires a human release. The latch survives restarts.
- **The LLM recommends; it cannot execute.** Every order passes deterministic gates: official
  eligible-token list, liquidity floor, stop-loss presence, position-size & concurrency caps,
  confidence floor, and a fee-aware min-edge check (calibrated to the confirmed ~0.15% cost).
- **Anti-churn** — re-entry and post-rejection cooldowns; quote → price-impact gate on every swap.
- **Compliance heartbeat** — the 1-trade/day rule is enforced by a scheduler outside LLM control,
  even while halted.
- **Default to inaction** — ambiguous signals, malformed LLM output, or API failures all become a
  logged hold, never a crash, never a blind trade.

## 🔌 Sponsor Stack (all three, integrated end-to-end)

| Tool | Role |
|---|---|
| **CMC Agent Hub** (MCP) | The entire signal layer: quotes & multi-timeframe momentum, global metrics (Fear & Greed, BTC dominance, altcoin season), market-cap TA, trending narratives, derivatives, and per-token **RSI / MACD / Fibonacci** |
| **Trust Wallet Agent Kit** | Self-custody agent wallet + all execution: spot swaps on BNB Chain via the TWAK MCP server (`swap`, quotes, balances, competition registration) |
| **BNB Smart Chain** | The on-chain venue for every trade; ARIA reads, decides, and executes end-to-end on-chain |

📄 Full strategy write-up: [docs/STRATEGY.md](docs/STRATEGY.md)

## 🏗️ Architecture

```
aria-agent/
├── aria/
│   ├── signals/          # CMC Agent Hub MCP client — signals only, no trading logic
│   ├── regime.py         # cached macro read → global risk posture
│   ├── brain/            # the LLM JUDGE (Claude) — approves/rejects one candidate
│   ├── strategies/       # propose-only: mean_reversion, breakout, narrative_rotation,
│   │                     #   preservation + per-candidate RSI/Fibonacci confirmation
│   ├── safety/           # circuit breaker, fee gate, trailing stop, compliance, window
│   ├── execution/        # the ONLY module that moves money — TWAK client + paper engine
│   ├── state/            # SQLite: decisions (full audit), trades, portfolio, price history
│   ├── api.py            # FastAPI — dashboard read window + operator controls
│   └── main.py           # the two-speed loop: fetch → exits → gates → confirm → judge → execute
├── dashboard/            # React + Vite + Tailwind: landing page + live terminal
├── tests/                # 190 tests incl. circuit-breaker integration (run on fixtures)
└── docs/                 # STRATEGY.md, DESIGN.md
```

## 🚀 Getting Started

```bash
# 1. Clone
git clone https://github.com/NueloSE/aria-agent.git && cd aria-agent

# 2. Python env (3.12+)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3. Secrets (copy template, fill in your keys)
cp deploy/env.example .env

# 4. Tests (fixtures only — no live calls, no keys needed)
SIGNALS_MODE=fixtures .venv/bin/pytest tests/ -q

# 5. Run the agent (dry-run: never executes)
.venv/bin/python -m aria.main --dry-run

# 6. Paper trading (simulated fills on live signals, no funds)
BRAIN_MODE=live ./scripts/paper_trade.sh
```

Real execution requires `EXECUTION_MODE=live`, `NETWORK=mainnet`, **and** the absence of
`--dry-run` — all three, by design. All secrets live in `.env` (git-ignored). The trading
wallet is a dedicated wallet used exclusively for this hackathon.

## 📊 Dashboard

`/` is the story; `/dashboard` is the live terminal: portfolio value & return, realized /
unrealized PnL, the risk posture and Fear & Greed, open positions marked against their
take-profit / stop levels, a filterable decision log with the LLM judge's reasoning, the
trade-performance ledger, and operator controls (window, emergency stop, halt release).

## 🏆 Hackathon Context

- **Event:** BNB Hack: AI Trading Agent Edition (DoraHacks)
- **Live window:** June 22–28, 2026 on BNB Chain — **spot-only**, via the TWAK swap interface
- **Scoring:** % return (start → end), with a ~30% max-drawdown disqualification gate
- **Confirmed cost model:** ~0.15% round-trip (organizer-set, simulated)
- **Rules encoded in the agent:** official eligible-token list, minimum 1 trade/day, stay-deployed, competition-window gating

## 📜 License

MIT

## ⚠️ Disclaimer

ARIA is experimental software built for a hackathon. It is not financial advice and not a
production trading system. Trading cryptocurrencies involves substantial risk of loss.
