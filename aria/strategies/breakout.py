"""Breakout / momentum entry — buy a quality token breaking UP on real volume.

Covers the recovering & trending markets that the counter-trend oversold-reclaim play
misses, so ARIA finds quality setups across more of the cycle (not just in fear). Cheap
quote-field gates find the candidate; per-candidate TA then confirms (RSI not overbought,
Fibonacci extension target). Reuses the MR quality gates. Strategies PROPOSE; never execute.
"""
from __future__ import annotations

from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.signals.parsing import parse_pct, parse_usd
from aria.strategies.base import Proposal, hold_proposal

_NON_TARGETS = frozenset(config.STABLES) | {"DAI", "TUSD", "FDUSD", "USDD", "USD1",
                                            "USDe", "USDF", "USDf", "FRAX", "EURI"}


def _score(q: dict) -> float:
    """Reward the strength of the move + the volume confirming it, lightly favoring a
    fresher breakout (lower 7d run = more room before it's chased)."""
    c24 = parse_pct(q.get("percent_change_24h")) or 0.0
    vchg = parse_pct(q.get("volume_change_24h")) or 0.0
    c7 = parse_pct(q.get("percent_change_7d")) or 0.0
    return c24 * 1.0 + min(max(vchg, 0.0), 200.0) * 0.05 - max(c7, 0.0) * 0.2


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
        c1h = parse_pct(q.get("percent_change_1h"))
        c24 = parse_pct(q.get("percent_change_24h"))
        c7 = parse_pct(q.get("percent_change_7d"))
        c90 = parse_pct(q.get("percent_change_90d"))
        c1y = parse_pct(q.get("percent_change_1y"))
        vchg = parse_pct(q.get("volume_change_24h"))
        vol = parse_usd(q.get("volume_24h"))
        rank = q.get("rank")
        if None in (c24, c7):
            continue
        if c24 < config.BO_MIN_24H_PCT:
            continue  # not moving up enough to be a breakout
        # quality gates (same as mean-reversion: no micro-caps, no dying tokens)
        if isinstance(rank, (int, float)) and rank > config.MR_MAX_RANK:
            trail.append(f"{sym}: rank {int(rank)} too small")
            continue
        if c1y is not None and c1y <= config.MR_MAX_1Y_DECLINE_PCT:
            trail.append(f"{sym}: structurally broken (1y {c1y:+.0f}%)")
            continue
        if c1y is None and c90 is not None and c90 <= config.MR_MAX_90D_DECLINE_PCT:
            trail.append(f"{sym}: structurally broken (90d {c90:+.0f}%)")
            continue
        if c1h is not None and c1h < config.BO_MIN_1H_PCT:
            trail.append(f"{sym}: reversing this hour (1h {c1h:+.1f}%)")
            continue
        if not (config.BO_MIN_7D_PCT <= c7 <= config.BO_MAX_7D_PCT):
            trail.append(f"{sym}: 7d {c7:+.0f}% out of base band")
            continue  # in freefall, or already ripped
        if vchg is not None and vchg < config.BO_MIN_VOL_CHANGE_PCT:
            trail.append(f"{sym}: weak volume ({vchg:+.0f}%) — not a real breakout")
            continue
        if vol is None or vol < config.BO_MIN_LIQUIDITY_USD:
            trail.append(f"{sym}: thin liquidity")
            continue
        candidates.append((_score(q), sym))
        trail.append(f"{sym}: breakout (24h {c24:+.1f}% vol {vchg if vchg is None else f'{vchg:+.0f}'}% 7d {c7:+.0f}%)")

    if not candidates:
        return hold_proposal("no breakout setup; " + ("; ".join(trail) or "nothing breaking out"))

    candidates.sort(reverse=True)
    token = candidates[0][1]
    return Proposal(
        action="buy",
        token_symbol=token,
        size_pct=config.BO_SIZE_PCT,
        stop_loss_pct=config.BO_STOP_LOSS_PCT,
        target_pct=config.BO_TARGET_PCT,
        rationale=f"breakout pick {token}; " + "; ".join(trail),
    )
