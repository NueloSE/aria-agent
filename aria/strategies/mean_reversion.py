"""Counter-trend mean reversion — oversold RECLAIM.

The pattern that makes money in fearful/ranging markets (Binacci's biggest
winners were all counter-trend "no macro light required"): buy an eligible blue
chip that is washed out AND has started turning back up. The reclaim is the
whole point — we never catch a falling knife; we wait for the bounce to begin.

Signals come straight from the quote fields we already fetch, so this costs ZERO
extra CMC calls. A real bottom is washed out AND reclaiming on returning volume —
not a tired dead-cat:
  - washed out:    30d change <= MR_STRETCH_30D_PCT   (deeply below the monthly mean)
  - reclaim 24h:   24h change >= MR_RECLAIM_24H_PCT    (turning back up over the day)
  - reclaim 1h:    1h change  >= MR_RECLAIM_1H_PCT     (still alive THIS hour — not rolling over)
  - not chasing:   7d change  <= MR_MAX_7D_RUN_PCT     (skip names that already ripped)
  - real volume:   24h volume change >= MR_MIN_VOL_CHANGE_PCT  (accumulation, not a fading bounce)
  - liquid:        24h volume >= MR_MIN_LIQUIDITY_USD

The score rewards washout depth + a live multi-timeframe reclaim on rising volume,
and penalizes names that have already recovered. Every entry carries a take-profit
target that clears the fee gate and a stop. Strategies PROPOSE; they never execute.
"""
from __future__ import annotations

from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.signals.parsing import parse_pct, parse_usd
from aria.strategies.base import Proposal, hold_proposal

_NON_TARGETS = frozenset(config.STABLES) | {"DAI", "TUSD", "FDUSD", "USDD", "USD1",
                                            "USDe", "USDF", "USDf", "FRAX", "EURI"}


def _score(q: dict) -> float:
    """Pick the EARLY oversold bounce on REAL volume: heavily reward the 30d washout
    depth, count the 24h/1h turn as (capped) confirmation that the bounce is live,
    reward returning volume (accumulation), and penalize names already recovered on 7d."""
    c7 = parse_pct(q.get("percent_change_7d")) or 0.0
    c24 = parse_pct(q.get("percent_change_24h")) or 0.0
    c1h = parse_pct(q.get("percent_change_1h")) or 0.0
    c30 = parse_pct(q.get("percent_change_30d")) or 0.0
    vchg = parse_pct(q.get("volume_change_24h")) or 0.0
    return (
        (-c30) * config.MR_W_WASHOUT
        + min(c24, 3.0) * config.MR_W_RECLAIM_24H
        + min(max(c1h, 0.0), 2.0) * config.MR_W_RECLAIM_1H
        + min(max(vchg, 0.0), 100.0) * config.MR_W_VOLUME
        - max(c7, 0.0) * config.MR_W_CHASE_PENALTY
    )


def propose(snapshot: MarketSnapshot, portfolio: PortfolioState,
            skip: "set[str] | None" = None) -> Proposal:
    trail: list[str] = []
    held = {p.token_symbol for p in portfolio.positions}
    skip = skip or set()
    candidates: list[tuple[float, str]] = []

    for sym in config.BLUE_CHIPS:
        if sym in _NON_TARGETS or sym in held or sym in skip:
            continue
        q = snapshot.token_quotes.get(sym)
        if not q:
            continue
        c7 = parse_pct(q.get("percent_change_7d"))
        c30 = parse_pct(q.get("percent_change_30d"))
        c24 = parse_pct(q.get("percent_change_24h"))
        c1h = parse_pct(q.get("percent_change_1h"))
        c90 = parse_pct(q.get("percent_change_90d"))
        c1y = parse_pct(q.get("percent_change_1y"))
        vchg = parse_pct(q.get("volume_change_24h"))
        vol = parse_usd(q.get("volume_24h"))
        rank = q.get("rank")
        if None in (c7, c30, c24):
            continue
        if c30 > config.MR_STRETCH_30D_PCT:
            continue  # not washed out on the month
        # Quality gates — exclude dying / micro-cap names (the IP failure mode):
        if isinstance(rank, (int, float)) and rank > config.MR_MAX_RANK:
            trail.append(f"{sym}: rank {int(rank)} > {config.MR_MAX_RANK} — too small for counter-trend")
            continue
        if c1y is not None and c1y <= config.MR_MAX_1Y_DECLINE_PCT:
            trail.append(f"{sym}: structurally broken (1y {c1y:+.0f}%) — falling knife, not reversion")
            continue
        if c1y is None and c90 is not None and c90 <= config.MR_MAX_90D_DECLINE_PCT:
            trail.append(f"{sym}: structurally broken (90d {c90:+.0f}%) — falling knife, not reversion")
            continue
        # Reclaim on EITHER timeframe: 24h turned up, OR the 1h turned up early (catches
        # the bottom a cycle sooner the moment the market stabilizes) — more setups.
        reclaim_24h = c24 >= config.MR_RECLAIM_24H_PCT
        reclaim_1h = c1h is not None and c1h >= config.MR_RECLAIM_1H_TURN_PCT
        if not (reclaim_24h or reclaim_1h):
            trail.append(f"{sym}: washed out but no reclaim (24h {c24:+.1f}% 1h {c1h if c1h is None else f'{c1h:+.1f}'}%)")
            continue  # still falling on both — NO knife catching
        if c1h is not None and c1h < config.MR_RECLAIM_1H_PCT:
            trail.append(f"{sym}: rolling over (1h {c1h:+.1f}%) — dead-cat guard")
            continue  # bounce already fading this hour
        if c7 > config.MR_MAX_7D_RUN_PCT:
            trail.append(f"{sym}: already ripped (7d {c7:+.0f}%) — no chasing")
            continue
        if vchg is not None and vchg < config.MR_MIN_VOL_CHANGE_PCT:
            trail.append(f"{sym}: volume collapsing (24h vol {vchg:+.0f}%) — weak bounce")
            continue  # reclaim on fading volume is unreliable
        if vol is None or vol < config.MR_MIN_LIQUIDITY_USD:
            trail.append(f"{sym}: liquidity {vol} below floor")
            continue
        candidates.append((_score(q), sym))
        trail.append(f"{sym}: oversold-reclaim (1h {c1h if c1h is None else f'{c1h:+.1f}'}% "
                     f"24h {c24:+.1f}% 7d {c7:+.0f}% 30d {c30:+.0f}% vol {vchg if vchg is None else f'{vchg:+.0f}'}%)")

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
