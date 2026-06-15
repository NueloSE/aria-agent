# ARIA — Adaptive Regime Intelligence Agent

> An autonomous AI trading agent that reads the market's regime first — then decides how to play it.

Built for **BNB Hack: AI Trading Agent Edition** (June 2026) — Track 1: Autonomous Trading Agents.

Organized by BNB Chain × CoinMarketCap × Trust Wallet.

---

## 🧠 What is ARIA?

Most trading agents run one fixed strategy. A momentum bot that thrives in a trending market becomes a loss engine the moment the market starts ranging. ARIA is different: it synthesizes the **market regime** from live signals before every decision, then routes capital to the strategy built for that regime — and treats *not trading* as a position.

```
                ┌─────────────────────────────────┐
                │   CMC Agent Hub (MCP signals)    │
                │ sentiment · TA · narratives ·    │
                │ derivatives · macro events       │
                └──────────────┬──────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │   LLM Reasoning Brain        │
                │   (Claude)                   │
                │   "Which regime are we in?   │
                │    Cite the evidence."       │
                └──────────────┬──────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌────────────────┐    ┌─────────────────┐
│ 🟢 TRENDING    │    │ 🟡 RANGING      │    │ 🔴 HIGH RISK     │
│ Narrative     │    │ Stand          │    │ Capital         │
│ Rotation      │    │ Aside          │    │ Preservation    │
└───────┬───────┘    └────────┬───────┘    └────────┬────────┘
        └──────────────────────┼──────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Strategy gates + Safety     │
                │  layer (VETO POWER)          │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Trust Wallet Agent Kit      │
                │  → spot swaps on BSC (MCP)   │
                └─────────────────────────────┘
```

## ⚡ The Strategy Modes

| Mode | Trigger | Strategy |
|------|---------|----------|
| 🟢 **Narrative Rotation** | regime = trending | Buy the strongest trending narrative's most liquid token from the official eligible list. Stop-loss on every entry. |
| 🟡 **Stand Aside** | regime = ranging | No durable direction = no edge after transaction costs. Doing nothing **is** the strategy. |
| 🔴 **Capital Preservation** | regime = high risk | Close positions, hold stables, wait. Surviving the week is most of winning it. |

(A mean-reversion mode exists in the codebase but is disabled: with simulated round-trip costs, tight-band reversion has no edge. Strategy honesty over feature count.)

## 🛡️ Safety First — the rule engine outranks the model

Track 1 is ranked on **% return with a ~30% max-drawdown disqualification gate**. ARIA treats that as a first-class constraint:

- **Hard circuit breaker** — at 20% drawdown (well inside the 30% gate) ARIA closes everything, halts, and requires a human `--clear-halt` to resume. The latch survives restarts.
- **The LLM recommends; it cannot execute.** Every order passes deterministic gates: official 149-token eligibility, liquidity floor, stop-loss presence, position-size cap, confidence floor.
- **Quote gate** — every swap is quoted first; price impact above threshold aborts the trade.
- **Compliance heartbeat** — the competition's 1-trade/day rule is enforced by a scheduler outside LLM control (small USDT↔ETH round trip), even while halted.
- **Default to inaction** — ambiguous signals, malformed LLM output, API failures: every failure path becomes a logged hold, never a crash, never a blind trade.

## 🔌 Sponsor Stack (all three integrated)

| Tool | Role |
|------|------|
| **CMC Agent Hub** (MCP server) | Market signals: global metrics (Fear & Greed, Altcoin Season, dominance), technical analysis, trending narratives, derivatives data, macro events — ARIA's LLM synthesizes the market regime from these |
| **Trust Wallet Agent Kit** | Self-custody agent wallet + all trade execution via the TWAK MCP server (`swap`, quotes, balances, competition registration) |
| **BNB AI Agent SDK** | ARIA is registered as an on-chain ERC-8004 agent identity on BSC |

## 🏗️ Architecture

```
aria-agent/
├── aria/
│   ├── signals/          # CMC Agent Hub MCP client — signals only, no trading logic
│   ├── brain/            # LLM regime synthesis → validated Decision schema
│   ├── strategies/       # propose-only: narrative rotation, preservation (+ disabled MR)
│   ├── safety/           # circuit breaker latch, compliance heartbeat, trading window
│   ├── execution/        # the ONLY module that moves money — TWAK MCP client
│   ├── state/            # SQLite: decisions (full audit), trades, portfolio snapshots
│   ├── api.py            # FastAPI — dashboard's read window + operator controls
│   └── main.py           # the loop: fetch → reason → gate → veto → execute → log
├── dashboard/            # React + Vite + Tailwind: landing page + live terminal
├── tests/                # 110+ tests incl. circuit-breaker integration (runs on fixtures)
├── probes/               # vendor-API probes (re-runnable; how we mapped the real APIs)
└── docs/DESIGN.md        # design rules & competition notes
```

## 🔄 The Agent Loop

Every cycle (default 30 min):

1. **Fetch** — live signals from CMC Agent Hub (failure policy: no signals → no trading; 3 consecutive failures → close to stables)
2. **Reason** — the LLM synthesizes the regime from the evidence, cites which signals drove the call, proposes at most one action
3. **Gate** — the mode's strategy concretizes the idea through deterministic gates (eligibility, liquidity, momentum); a hallucinated token cannot survive
4. **Veto** — the safety layer validates against the breaker, caps, and floors; vetoes become logged holds
5. **Execute** — quote → impact check → spot swap via TWAK on BSC
6. **Log** — every decision (including "do nothing") recorded with the full reasoning chain

## 📊 Dashboard

`/` is the story; `/dashboard` is the terminal: current regime + the LLM's cited reasoning, portfolio curve plotted against the 20% halt and 30% DQ lines, the full decision log, and operator controls (competition window, emergency stop, halt release) — all changes apply within one cycle, no restarts.

## 🚀 Getting Started

```bash
# 1. Clone
git clone https://github.com/NueloSE/aria-agent.git
cd aria-agent

# 2. Python env (3.12+)
python3.13 -m venv .venv
.venv/bin/pip install -e . pytest pytest-asyncio fastapi 'uvicorn[standard]'

# 3. Secrets (copy template, fill in your keys)
cp .env.example .env

# 4. Run the agent (dry-run: never executes trades)
.venv/bin/python -m aria.main --dry-run

# 5. Tests (fixtures only — no live calls, no keys needed)
SIGNALS_MODE=fixtures .venv/bin/pytest tests/ -q

# 6. Dashboard (two terminals)
.venv/bin/uvicorn aria.api:app --port 8000
cd dashboard && npm install && npm run dev   # → http://localhost:5173
```

### Required environment variables

See [.env.example](.env.example) — Anthropic key (brain), CMC key (signals),
TWAK wallet password (execution), plus risk parameters. Real execution additionally
requires `EXECUTION_MODE=live`, `NETWORK=mainnet`, **and** the absence of `--dry-run` —
all three, by design.

> ⚠️ **Security:** All secrets live in `.env` (git-ignored). The trading wallet is a dedicated, freshly created wallet used exclusively for this hackathon.

## 🏆 Hackathon Context

- **Event:** BNB Hack: AI Trading Agent Edition (DoraHacks)
- **Live trading window:** June 22–28, 2026 on BSC — spot-only, via the TWAK swap interface
- **Scoring:** % return (start → end capital), with a ~30% max-drawdown disqualification gate
- **Rules encoded in the agent:** official 149-token eligible list, minimum 1 trade/day, stay-deployed requirement, competition window gating

## 📜 License

MIT

## ⚠️ Disclaimer

ARIA is experimental software built for a hackathon. It is not financial advice and not a production trading system. Trading cryptocurrencies involves substantial risk of loss. Use at your own risk.
