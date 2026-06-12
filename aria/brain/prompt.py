"""Prompt construction for the reasoning brain.

Design: the LLM's job is SYNTHESIS — CMC gives raw-ish signals, not a regime label.
The model must (1) classify the regime from conflicting evidence, citing which
signals drove the call, (2) route to a mode, (3) propose an action the safety
layer will independently re-validate. The system prompt is static (cache-friendly);
all volatile data goes in the user message.
"""
from __future__ import annotations

import json
from typing import Optional, Sequence

from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.signals.parsing import parse_pct

SYSTEM_PROMPT = f"""You are ARIA, an autonomous spot-trading agent competing in a \
one-week live trading competition on BNB Smart Chain. You are scored on raw total \
return, but exceeding {config.MAX_DRAWDOWN_PCT:.0f}% drawdown DISQUALIFIES you. \
Surviving with modest gains beats blowing up. Trades incur meaningful simulated \
costs (assume ~1.5% per round trip until told otherwise), so trade RARELY and only \
with conviction — a few high-quality trades beat many mediocre ones.

YOUR TASK each cycle: synthesize the market REGIME from the signals provided, then \
route to a strategy mode and propose at most one action.

REGIME DEFINITIONS — classify from evidence, cite the signals that drove your call:
- "trending": sustained directional momentum. Evidence: market-cap above short EMAs, \
MACD positive and rising, healthy F&G (40-75), narratives with strong 7d/30d momentum \
and broad volume.
- "ranging": no durable direction. Evidence: price oscillating around flat MAs, \
RSI mid-band, mixed narrative performance, F&G mid-range.
- "high_risk": elevated probability of sharp drawdown. Evidence: extreme F&G \
(<=25 or >=85), heavy 7d/30d market declines, falling open interest with rising \
liquidations, imminent high-impact macro events, funding stress.

MODES:
- "narrative_rotation" (only in trending): buy the strongest trending narrative's \
most liquid eligible token.
- "preservation" (ranging or high_risk): hold stables / close positions. In ranging \
markets with no edge, doing nothing IS the strategy.
- "mean_reversion": currently DISABLED — never select it.

ACTIONS: "buy" (requires token_symbol, size_pct, stop_loss_pct), "sell" (requires \
token_symbol), "close_all", "hold".

HARD CONSTRAINTS (the safety layer enforces these; violations are vetoed and logged \
against you):
- Only tokens from the eligible list may be traded. BNB/WBNB/BTC/BTCB are NOT eligible.
- size_pct <= {config.MAX_POSITION_PCT:.0f} (% of portfolio per trade)
- every buy needs stop_loss_pct > 0
- confidence < {config.CONFIDENCE_FLOOR} is treated as hold
- if portfolio drawdown >= {config.HALT_DRAWDOWN_PCT:.0f}%, only close_all/hold pass

DISCIPLINE:
- Default to inaction. Ambiguity = hold with low confidence.
- Never average down into a falling position.
- In your reasoning, name the 2-4 specific signals that determined your regime call, \
and note the strongest piece of evidence AGAINST your call.
"""


def _narrative_digest(snapshot: MarketSnapshot, top_n: int = 5) -> list[dict]:
    out = []
    for n in snapshot.narratives[:top_n]:
        top_coins = n.get("topCoinList", {})
        coins = [r[0] for r in top_coins.get("rows", [])] if isinstance(top_coins, dict) else []
        out.append({
            "rank": n.get("trendingRank"),
            "name": n.get("categoryName"),
            "mcap_24h": n.get("marketCapChangePercentage24h"),
            "mcap_7d": n.get("marketCapChangePercentage7d"),
            "mcap_30d": n.get("marketCapChangePercentage30d"),
            "vol_vs_market_7d": n.get("volumeWeightedPricePerfVsCryptoMarketCap7d"),
            "top_coins": coins,
        })
    return out


def _quotes_digest(snapshot: MarketSnapshot) -> dict:
    out = {}
    for sym, q in snapshot.token_quotes.items():
        out[sym] = {
            "price": q.get("price"),
            "pct_24h": q.get("percent_change_24h"),
            "pct_7d": q.get("percent_change_7d"),
            "pct_30d": q.get("percent_change_30d"),
        }
    return out


def _macro_digest(snapshot: MarketSnapshot, top_n: int = 5) -> list[dict]:
    return [
        {"title": e.get("title"), "date": e.get("eventDate")}
        for e in snapshot.macro_events[:top_n]
    ]


def build_user_message(
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    history: Optional[Sequence[dict]] = None,
) -> str:
    payload = {
        "signals": {
            "fear_greed": {
                "index": snapshot.fear_greed_index,
                "label": snapshot.fear_greed_label,
            },
            "total_mcap_pct_change": {
                "24h": snapshot.total_mcap_change_24h_pct,
                "7d": snapshot.total_mcap_change_7d_pct,
            },
            "mcap_technical_analysis": snapshot.mcap_ta,
            "derivatives": snapshot.derivatives,
            "trending_narratives": _narrative_digest(snapshot),
            "upcoming_macro_events": _macro_digest(snapshot),
            "tracked_token_quotes": _quotes_digest(snapshot),
        },
        "portfolio": {
            "total_value_usd": portfolio.total_value_usd,
            "drawdown_pct": round(portfolio.drawdown_pct, 2),
            "positions": [
                {"token": p.token_symbol, "amount": p.amount,
                 "entry_usd": p.entry_price_usd, "stop_loss_pct": p.stop_loss_pct}
                for p in portfolio.positions
            ],
            "stable_balance_usd": portfolio.stable_balance_usd,
            "trades_today": portfolio.trades_today,
        },
        "recent_decisions": list(history or [])[:5],
        # full official list (~1KB) — never let the model guess eligibility
        "eligible_tokens": sorted(config.ELIGIBLE_SYMBOLS),
    }
    return json.dumps(payload, default=str)
