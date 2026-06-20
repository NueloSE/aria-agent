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
Surviving with modest gains beats blowing up. Trading costs are LOW \
(~{config.round_trip_cost_pct():.2f}% round-trip), so cost is NOT a barrier — trade \
on QUALITY, not rarity: take every genuine setup, but never force a bad one. Many \
small disciplined wins compound; a blow-up disqualifies you.

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

MODES — you have TWO offensive plays plus a defensive one. Pick the one the market \
is offering. Being idle every cycle is itself a losing strategy in a % return \
competition; take GOOD setups when they exist, stay out when they don't.
- "narrative_rotation" (trending markets): buy the strongest trending narrative's \
most liquid eligible token. Momentum play — needs a trend.
- "mean_reversion" (ranging OR high_risk markets): COUNTER-TREND. Buy an eligible \
blue chip that is washed out (deeply down over 7d/30d) AND has started turning back \
up (positive 24h) — a capitulation bounce. The strategy gate confirms the setup and \
picks the token; you just route here when the market is oversold-and-reclaiming. \
This is the play for fearful, non-trending markets — DO NOT default to preservation \
just because sentiment is fearful; an oversold market that's bouncing is a buy.
- "preservation" (no edge in either direction): hold stables / close positions. \
Correct when the market is falling with no reclaim, or genuinely directionless.

ACTIONS: "buy" (requires token_symbol OR null to let the gate pick; size_pct; \
stop_loss_pct; AND a take-profit target via reasoning), "sell", "close_all", "hold".

TAKE-PROFIT TARGETS: round-trip cost is only ~{config.round_trip_cost_pct():.2f}%, so \
even small moves (1-2%) are net-profitable. The strategy sets concrete targets/stops \
off real structure; your job is to enter when a genuine bounce/breakout is plausible — \
you no longer need a large move to justify the trade.

ELIGIBILITY — READ CAREFULLY:
The user message contains an `eligible_tokens` array. That list is AUTHORITATIVE and \
COMPLETE. A token is tradeable if and only if its symbol appears in that array — \
nothing else. Do NOT judge eligibility from prior knowledge or assume a major coin \
is in or out: CHECK THE LIST. Many blue chips (e.g. ETH, XRP, LINK, ADA) ARE on it; \
some you'd expect (BTC, BNB, and any WBNB/BTCB wrappers) are NOT. When you mention a \
token's eligibility in your reasoning, verify it against the array first — do not state \
a token is ineligible unless it is genuinely absent from the list.

HARD CONSTRAINTS (the safety layer enforces these; violations are vetoed and logged \
against you):
- Only tokens present in the eligible_tokens array may be traded.
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


JUDGE_SYSTEM_PROMPT = f"""You are ARIA's entry judge in a one-week live spot-trading \
competition on BNB Smart Chain. You are scored on raw total return, but exceeding \
{config.MAX_DRAWDOWN_PCT:.0f}% drawdown DISQUALIFIES you — survival beats greed.

A DETERMINISTIC strategy gate has already found ONE concrete entry candidate: a \
specific eligible token, with a stop-loss and a structure-based take-profit target. \
Trading costs are negligible (~{config.round_trip_cost_pct():.2f}% round-trip), so a \
small-but-genuine move is worth taking. The token selection is NOT your job and you \
cannot change it. YOUR ONLY job is to APPROVE or REJECT this single setup using the \
broader market regime, and optionally trim its size.

You are the judgment layer the mechanical gate lacks. Reject when the macro picture \
makes THIS entry a bad idea even though the per-token signal looks fine, for example:
- the whole market is sliding / risk-off and this would be catching a market-wide knife,
- an imminent high-impact macro event makes new risk reckless,
- breadth/derivatives stress (falling open interest + rising liquidations) signals a cascade,
- the candidate's bounce looks like a dead-cat inside a clear downtrend.

Approve when the setup is coherent with the regime: an oversold reclaim while the broader \
tape is stabilizing, or genuine momentum in a healthy trend. Because costs are tiny, \
APPROVE genuine setups freely — don't reject a real bounce/breakout out of excess caution. \
Reserve rejection for setups the macro actively contradicts (the cases listed above).

Output: approve (bool), confidence (0-1; below {config.CONFIDENCE_FLOOR} is treated as a \
reject), an optional size_pct to trim the gate's size (never raise it), and a one-line \
reasoning naming the 1-3 macro signals that drove your call.
"""


def build_judge_message(candidate, snapshot: MarketSnapshot,
                        portfolio: PortfolioState, posture) -> str:
    """User message for the entry judge: the concrete candidate + macro context."""
    payload = {
        "candidate": {
            "token": candidate.token_symbol,
            "size_pct": candidate.size_pct,
            "stop_loss_pct": candidate.stop_loss_pct,
            "take_profit_pct": candidate.target_pct,
            "gate_rationale": candidate.rationale,
        },
        "global_risk_posture": {
            "label": posture.label, "reason": posture.reason,
            "size_multiplier": posture.size_multiplier,
        },
        "macro_context": {
            "fear_greed": {"index": snapshot.fear_greed_index,
                           "label": snapshot.fear_greed_label},
            "total_mcap_pct_change": {"24h": snapshot.total_mcap_change_24h_pct,
                                      "7d": snapshot.total_mcap_change_7d_pct},
            "mcap_technical_analysis": snapshot.mcap_ta,
            "derivatives": snapshot.derivatives,
            "rotation": _rotation_digest(snapshot),
            "upcoming_macro_events": _macro_digest(snapshot),
            "candidate_quote": snapshot.token_quotes.get(candidate.token_symbol or ""),
        },
        "portfolio": {
            "total_value_usd": portfolio.total_value_usd,
            "drawdown_pct": round(portfolio.drawdown_pct, 2),
            "open_positions": [p.token_symbol for p in portfolio.positions],
        },
    }
    return json.dumps(payload, default=str)


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


def _rotation_digest(snapshot: MarketSnapshot) -> dict:
    """BTC dominance + altcoin-season rotation (Binacci's high-weight regime signal):
    rising BTC.D = defensive/risk-off; falling = risk-on toward alts."""
    g = (snapshot.raw or {}).get("global_metrics", {}) or {}
    dom = g.get("dominance", {}) or {}
    btc = dom.get("btc", {}) or {}
    rot = (g.get("rotation", {}) or {}).get("altcoin_season", {}) or {}
    return {
        "btc_dominance": btc.get("current"),
        "btc_dominance_history": btc.get("history"),  # yesterday / last_week / last_month
        "altcoin_season": rot.get("current") or rot.get("index") or rot.get("value"),
    }


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
            "rotation": _rotation_digest(snapshot),
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
