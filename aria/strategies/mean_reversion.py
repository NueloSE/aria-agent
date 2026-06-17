"""Counter-trend mean reversion — oversold RECLAIM.

The pattern that makes money in fearful/ranging markets (Binacci's biggest
winners were all counter-trend "no macro light required"): buy an eligible blue
chip that is washed out AND has started turning back up. The reclaim is the
whole point — we never catch a falling knife; we wait for the bounce to begin.

Signals come straight from the quote %-change fields we already fetch, so this
costs ZERO extra CMC calls:
  - washed out:  30d change <= MR_STRETCH_30D_PCT  (deeply below the monthly mean)
  - reclaim:     24h change >= MR_RECLAIM_24H_PCT   (turning back up NOW)
  - not chasing: 7d change <= MR_MAX_7D_RUN_PCT     (skip names that already ripped)

Every entry carries a take-profit target that clears the fee gate and a stop.
Strategies PROPOSE; they never execute.
"""
from __future__ import annotations

from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.signals.parsing import parse_pct, parse_usd
from aria.strategies.base import Proposal, hold_proposal

_NON_TARGETS = frozenset(config.STABLES) | {"DAI", "TUSD", "FDUSD", "USDD", "USD1",
                                            "USDe", "USDF", "USDf", "FRAX", "EURI"}


def _score(q: dict) -> float:
    """Pick the EARLY oversold bounce: heavily reward the 30d washout depth, count
    the 24h turn only as confirmation (capped — a +13% rip is no better than a
    clean +3% turn), and penalize names that have already recovered on 7d."""
    c7 = parse_pct(q.get("percent_change_7d")) or 0.0
    c24 = parse_pct(q.get("percent_change_24h")) or 0.0
    c30 = parse_pct(q.get("percent_change_30d")) or 0.0
    return (-c30) * 1.0 + min(c24, 3.0) * 1.0 - max(c7, 0.0) * 0.5


def propose(snapshot: MarketSnapshot, portfolio: PortfolioState) -> Proposal:
    trail: list[str] = []
    held = {p.token_symbol for p in portfolio.positions}
    candidates: list[tuple[float, str]] = []

    for sym in config.BLUE_CHIPS:
        if sym in _NON_TARGETS or sym in held:
            continue
        q = snapshot.token_quotes.get(sym)
        if not q:
            continue
        c7 = parse_pct(q.get("percent_change_7d"))
        c30 = parse_pct(q.get("percent_change_30d"))
        c24 = parse_pct(q.get("percent_change_24h"))
        vol = parse_usd(q.get("volume_24h"))
        if None in (c7, c30, c24):
            continue
        if c30 > config.MR_STRETCH_30D_PCT:
            continue  # not washed out on the month
        if c24 < config.MR_RECLAIM_24H_PCT:
            trail.append(f"{sym}: washed out but no reclaim (24h {c24:+.1f}%)")
            continue  # still falling — NO knife catching
        if c7 > config.MR_MAX_7D_RUN_PCT:
            trail.append(f"{sym}: already ripped (7d {c7:+.0f}%) — no chasing")
            continue
        if vol is None or vol < config.MR_MIN_LIQUIDITY_USD:
            trail.append(f"{sym}: liquidity {vol} below floor")
            continue
        candidates.append((_score(q), sym))
        trail.append(f"{sym}: oversold-reclaim (7d {c7:+.0f}% 30d {c30:+.0f}% 24h {c24:+.1f}%)")

    if not candidates:
        return hold_proposal("no oversold-reclaim setup; " + ("; ".join(trail) or "nothing washed out"))

    candidates.sort(reverse=True)
    token = candidates[0][1]
    return Proposal(
        action="buy",
        token_symbol=token,
        size_pct=config.MR_SIZE_PCT,
        stop_loss_pct=config.MR_STOP_LOSS_PCT,
        target_pct=config.MR_TARGET_PCT,
        rationale=f"mean-reversion pick {token}; " + "; ".join(trail),
    )
