"""Narrative rotation: buy the strongest trending narrative's best eligible token.

Gate chain (every exclusion is logged in the rationale):
  1. narrative gate  — top-ranked narrative with positive 7d momentum
  2. eligibility     — candidate ∩ official 149-token list (outer gate, absolute)
  3. quote data      — no quote data = no trade (default to inaction)
  4. liquidity       — 24h volume >= NR_MIN_LIQUIDITY_USD
  5. preference      — brain's suggested token honored IF it survived gates 2-4
Token risk check (twak check_token_risk) is applied at execution time in Stage 7.
"""
from __future__ import annotations

from typing import Optional

from aria import config
from aria.models import MarketSnapshot, PortfolioState
from aria.signals.parsing import parse_pct, parse_usd
from aria.strategies.base import Proposal, hold_proposal

# Stables never qualify as a "rotation" target even though they're eligible
_NON_TARGETS = frozenset(config.STABLES) | {"DAI", "TUSD", "FDUSD", "USDD", "USD1", "USDe"}


def _narrative_momentum_ok(n: dict) -> bool:
    pct_7d = parse_pct(n.get("marketCapChangePercentage7d"))
    return pct_7d is not None and pct_7d > 0


def _candidates_from(narrative: dict) -> list[str]:
    top = narrative.get("topCoinList", {})
    rows = top.get("rows", []) if isinstance(top, dict) else []
    return [str(r[0]).upper() for r in rows if r]


def propose(
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    preferred_token: Optional[str] = None,
) -> Proposal:
    trail: list[str] = []

    # Gate 1: pick the best narrative with real momentum
    narrative = None
    for n in snapshot.narratives:
        if _narrative_momentum_ok(n):
            narrative = n
            break
        trail.append(f"narrative '{n.get('categoryName')}' rejected: 7d momentum "
                     f"{n.get('marketCapChangePercentage7d')}")
    if narrative is None:
        return hold_proposal("no narrative with positive 7d momentum; " + "; ".join(trail))
    trail.append(f"narrative: {narrative.get('categoryName')} "
                 f"(7d {narrative.get('marketCapChangePercentage7d')})")

    # Gates 2-4 over the narrative's top coins
    survivors: list[str] = []
    for sym in _candidates_from(narrative)[: config.NR_TOP_TOKENS_PER_NARRATIVE * 3]:
        if sym not in config.ELIGIBLE_SYMBOLS:
            trail.append(f"{sym}: not on eligible list")
            continue
        if sym in _NON_TARGETS:
            trail.append(f"{sym}: stable, not a rotation target")
            continue
        quote = snapshot.token_quotes.get(sym)
        if not quote:
            trail.append(f"{sym}: no quote data -> excluded (default to inaction)")
            continue
        vol = parse_usd(quote.get("volume_24h"))
        if vol is None or vol < config.NR_MIN_LIQUIDITY_USD:
            trail.append(f"{sym}: 24h volume {vol} below {config.NR_MIN_LIQUIDITY_USD:,.0f}")
            continue
        survivors.append(sym)
        if len(survivors) >= config.NR_TOP_TOKENS_PER_NARRATIVE:
            break

    if not survivors:
        return hold_proposal("no candidate survived gates; " + "; ".join(trail))

    # Gate 5: brain preference honored only if it independently survived
    token = preferred_token.upper() if preferred_token else None
    if token in survivors:
        trail.append(f"brain preference {token} honored (passed all gates)")
    else:
        if token:
            trail.append(f"brain preference {token} did NOT survive gates; using top candidate")
        token = survivors[0]

    # Don't stack the same position
    held = {p.token_symbol for p in portfolio.positions}
    if token in held:
        return hold_proposal(f"already holding {token}; no averaging in; " + "; ".join(trail))

    return Proposal(
        action="buy",
        token_symbol=token,
        size_pct=min(config.MAX_POSITION_PCT, config.NR_MAX_NARRATIVE_ALLOCATION),
        stop_loss_pct=config.NR_STOP_LOSS_PCT,
        rationale="; ".join(trail),
    )
