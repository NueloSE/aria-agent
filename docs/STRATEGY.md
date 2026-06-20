# ARIA — Adaptive Regime Intelligence Agent

> **Read the regime first, then decide how to play it.** An autonomous spot-trading
> agent for BNB Hack Track 1, built end-to-end on **CoinMarketCap** signals,
> **Trust Wallet Agent Kit** execution, and **BNB Smart Chain**.

---

## TL;DR (submission summary)

ARIA is a regime-aware, spot-only trading agent. Each cycle it reads the live market
from the **CoinMarketCap Agent Hub**, derives a global risk posture, and runs three
deterministic entry strategies (oversold-reclaim, breakout, narrative-rotation). When a
strategy surfaces a candidate, ARIA confirms it with **real per-token technical analysis
(RSI + Fibonacci support/resistance)**, then an **LLM judge (Claude)** approves or rejects
it against the macro picture. Approved trades execute as spot swaps via **TWAK on BNB
Chain**. Exits (take-profit at the nearest Fibonacci level, a stepped trailing stop, and a
hard stop) plus a **drawdown circuit breaker** run mechanically every cycle — so ARIA
banks winners and cuts losers instantly, and is built first and foremost **not to blow up**.

---

## How it works — the pipeline

```
CMC Agent Hub ─▶ Regime & Posture ─▶ Strategy Gates ─▶ TA Confirmation ─▶ LLM Judge ─▶ Safety ─▶ TWAK swap (BNB Chain)
   (signals)        (risk stance)      (find candidate)   (RSI + Fib)      (approve?)   (veto)      (execute)
                                                │
                          Mechanical exits + drawdown breaker run every cycle (no LLM)
```

ARIA runs a **two-speed loop**: a fast deterministic loop (every ~30–90s) polls prices,
manages exits, and scans the strategy gates; the **LLM is event-driven** — called only
when a real candidate needs a judgment. This makes the agent responsive and cheap while
keeping the model's nuance exactly where it adds value.

---

## Reading the market — regime & the "LLM as judge" model

ARIA does **not** let the LLM trade freely. Instead:

- A cached **macro read** (Fear & Greed, BTC dominance, altcoin season, total-market
  trend) sets a coarse **risk posture**: `risk-on` / `neutral` / `cautious` / `risk-off`.
  In risk-off it takes no new entries; in cautious it runs counter-trend only, at half size.
- Deterministic gates then **find** a concrete candidate from CMC quote data.
- **Claude is the judge**, not the oracle: it sees the full macro context and the one
  candidate, and decides **approve / reject / trim size**. It can never invent a trade —
  it can only bless a setup the math already found, or veto it (e.g., a dead-cat inside a
  market-wide slide). This is cheaper, more responsive, and more robust than an
  LLM-decides-everything design.

---

## Three strategies — coverage across the whole cycle

| Strategy | Fires when… | Logic |
|---|---|---|
| **Oversold reclaim** (mean-reversion) | fearful / post-decline | buy washed-out, quality blue chips that are turning back up on returning volume |
| **Breakout / momentum** | recovering / trending | buy quality tokens breaking up on real volume, not overextended |
| **Narrative rotation** | a hot sector has momentum | buy the strongest trending CMC narrative's most liquid eligible token |
| **Capital preservation** | no edge | sit in stablecoins |

Every candidate then passes a **per-token technical confirmation** using the CMC Agent
Hub's analysis tool: **RSI** (genuine oversold for reclaims / not-overbought for
breakouts) gates the entry, and **Fibonacci levels + pivots** set a structure-aware
take-profit (nearest resistance) and stop (below support) — directly applying the
support/resistance the competition encourages.

---

## Risk discipline — built to survive the drawdown gate

Survival is the priority: exceeding the max-drawdown limit is disqualification, so ARIA's
risk layer is mechanical and always-on (no LLM in the loop):

- **Take-profit** at the structure-based target, a **stepped trailing stop** that walks
  into profit and locks winners, and a **hard stop-loss**.
- A **drawdown circuit breaker** that flattens everything and halts well *inside* the
  disqualification threshold.
- A hard **safety layer** that can veto any trade, enforces the official eligible-token
  list, sizes within caps, and is fee-aware (calibrated to the confirmed ~0.15%
  round-trip cost).
- **Re-entry cooldowns** to prevent churn, and a **compliance heartbeat** that guarantees
  the minimum-one-trade-per-day rule is met even while idle or halted.

---

## Full-stack integration

- **CoinMarketCap Agent Hub** — the entire signal layer: quotes & multi-timeframe momentum,
  global metrics (Fear & Greed, dominance, altseason), market-cap TA, trending narratives,
  derivatives (OI / funding / liquidations), and per-token RSI / MACD / **Fibonacci**.
- **Trust Wallet Agent Kit (TWAK)** — all execution: self-custody spot swaps on BNB Chain,
  with quote → price-impact gate → swap → reconcile.
- **BNB Smart Chain** — the on-chain venue for every trade.

ARIA reads, decides, and executes **end-to-end on-chain**, combining all three sponsor
technologies into a single disciplined, regime-aware agent.

---

*Spot-only, long-only, by competition rule. Scored on raw return; engineered to capture
real moves while never risking the drawdown gate.*
