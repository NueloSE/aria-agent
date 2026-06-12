# ARIA — Adaptive Regime Intelligence Agent

> An autonomous AI trading agent that reads the market's regime first — then decides how to play it.

Built for **BNB Hack: AI Trading Agent Edition** (June 2026) — Track 1: Autonomous Trading Agents.

Organized by BNB Chain × CoinMarketCap × Trust Wallet.

---

## 🧠 What is ARIA?

Most trading agents run one fixed strategy. A momentum bot that thrives in a trending market becomes a loss engine the moment the market starts ranging. ARIA is different: it classifies the **market regime** before every decision, then routes capital to the strategy built for that regime.

```
                ┌─────────────────────────────┐
                │   CMC Agent Hub (signals)    │
                │ regime · narratives · risk   │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │   LLM Reasoning Brain        │
                │   (Claude Sonnet)            │
                │   "Which regime are we in?   │
                │    Which strategy applies?"  │
                └──────────────┬──────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌────────────────┐    ┌─────────────────┐
│ 🟢 TRENDING    │    │ 🟡 RANGING      │    │ 🔴 HIGH RISK     │
│ Narrative     │    │ Mean           │    │ Capital         │
│ Rotation      │    │ Reversion      │    │ Preservation    │
└───────┬───────┘    └────────┬───────┘    └────────┬────────┘
        └──────────────────────┼──────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Safety Layer (circuit       │
                │  breakers — veto power)      │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Trust Wallet Agent Kit      │
                │  → swap on BSC (PancakeSwap) │
                └─────────────────────────────┘
```

## ⚡ The Three Strategy Modes

| Mode | Trigger | Strategy |
|------|---------|----------|
| 🟢 **Narrative Rotation** | CMC regime = trending | Identify the hottest crypto narrative (AI, RWA, DePIN…) via CMC sector momentum. Rotate into its most liquid BSC tokens. |
| 🟡 **Mean Reversion** | CMC regime = ranging | Trade blue-chip range oscillations — buy support, sell resistance, tight stops. |
| 🔴 **Capital Preservation** | CMC risk flags fire | Reduce/close positions, hold stables. The best trade is sometimes no trade. |

## 🛡️ Safety First (Drawdown Cap Compliance)

Track 1 agents are scored on live PnL **subject to a maximum drawdown cap**. ARIA treats this as a first-class constraint:

- **Hard circuit breaker** — if drawdown approaches the cap, all positions close and trading halts. The LLM recommends; the rule engine has veto power.
- **Position size limits** — no single trade can exceed a configured % of portfolio.
- **Liquidity-aware sizing** — CMC liquidity signals prevent oversized trades in thin markets.
- **Default to inaction** — when signals are ambiguous, ARIA does nothing.

## 🔌 Sponsor Stack (all three integrated)

| Tool | Role |
|------|------|
| **CMC Agent Hub** (MCP server) | Market signals: global metrics (Fear & Greed, Altcoin Season, dominance), technical analysis, trending narratives, derivatives data, macro events — ARIA's LLM synthesizes the market regime from these |
| **Trust Wallet Agent Kit** | Self-custody agent wallet + all trade execution (`twak swap … --chain bsc`) |
| **BNB AI Agent SDK** | ARIA is registered as an on-chain ERC-8004 agent identity on BSC |

## 🏗️ Architecture

```
aria-agent/
├── aria/
│   ├── signals/          # CMC Agent Hub client (MCP)
│   ├── brain/            # LLM reasoning loop + decision schema
│   ├── strategies/       # narrative_rotation.py, mean_reversion.py, preservation.py
│   ├── execution/        # Trust Wallet Agent Kit + BNB SDK integration
│   ├── safety/           # circuit breakers, position limits, drawdown monitor
│   ├── state/            # portfolio state, trade log (SQLite)
│   └── main.py           # the agent loop
├── dashboard/            # React monitoring UI
├── tests/
├── .env.example          # template — NEVER commit real .env
└── docs/DESIGN.md        # design rules & competition notes
```

## 🔄 The Agent Loop

Every cycle (configurable, default 30 min):

1. **Fetch** — pull fresh signals from CMC Agent Hub
2. **Reason** — LLM receives signals + portfolio state + recent history, outputs a structured decision with plain-English reasoning
3. **Validate** — safety layer checks the decision against circuit breakers
4. **Execute** — if approved, sign and submit the swap via Trust Wallet Agent Kit
5. **Log** — every decision (including "do nothing") recorded with full reasoning chain

## 📊 Dashboard

A lightweight React dashboard shows in real time: current regime classification, active strategy mode, open positions, PnL curve vs. drawdown cap, and the full decision log with LLM reasoning for every action.

## 🚀 Getting Started

```bash
# 1. Clone
git clone https://github.com/<your-username>/aria-agent.git
cd aria-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets (copy template, fill in your keys)
cp .env.example .env

# 4. Run on BSC TESTNET first
python -m aria.main --network testnet

# 5. Dashboard
cd dashboard && npm install && npm run dev
```

### Required environment variables

```
ANTHROPIC_API_KEY=        # LLM reasoning brain
CMC_MCP_API_KEY=          # CoinMarketCap MCP (X-CMC-MCP-API-KEY, from pro.coinmarketcap.com)
TWAK_WALLET_PASSWORD=     # unlocks the TWAK embedded agent wallet (dedicated hackathon wallet ONLY)
BSC_RPC_URL=              # BNB Smart Chain RPC endpoint
NETWORK=testnet           # testnet | mainnet
MAX_DRAWDOWN_PCT=30       # official DQ gate (~30%); agent halts at 20%
MAX_POSITION_PCT=         # max % of portfolio per trade
```

> ⚠️ **Security:** All secrets live in `.env`, which is git-ignored. The trading wallet is a dedicated, freshly created wallet used exclusively for this hackathon.

## 🏆 Hackathon Context

- **Event:** BNB Hack: AI Trading Agent Edition (DoraHacks)
- **Build window:** June 3–21, 2026
- **Live trading window:** June 22–28, 2026 on BSC
- **Scoring:** Real PnL, subject to a maximum drawdown cap
- **Track:** 1 — Autonomous Trading Agents

## 📜 License

MIT

## ⚠️ Disclaimer

ARIA is experimental software built for a hackathon. It is not financial advice and not a production trading system. Trading cryptocurrencies involves substantial risk of loss. Use at your own risk.
