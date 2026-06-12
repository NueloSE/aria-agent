"""Strategies PROPOSE trades; they never execute. One module per mode.

refine() is the router: the brain picks regime/mode and suggests; the mode's
strategy turns that into a concrete, gate-checked proposal. The brain can never
produce a trade the gates didn't independently approve."""
from __future__ import annotations

import logging

from aria import config
from aria.models import Decision, MarketSnapshot, PortfolioState
from aria.strategies import mean_reversion, narrative_rotation, preservation
from aria.strategies.base import Proposal

log = logging.getLogger("aria.strategies")


def _merge(decision: Decision, proposal: Proposal) -> Decision:
    return Decision(
        regime=decision.regime,
        mode=decision.mode,
        action=proposal.action,
        token_symbol=proposal.token_symbol,
        size_pct=min(proposal.size_pct, decision.size_pct or proposal.size_pct)
        if decision.action == "buy" and proposal.action == "buy"
        else proposal.size_pct,
        stop_loss_pct=proposal.stop_loss_pct,
        confidence=decision.confidence,
        reasoning=f"{decision.reasoning} | strategy: {proposal.rationale}",
    )


async def _enrich_candidate_quotes(snapshot: MarketSnapshot) -> None:
    """Fetch quotes for eligible narrative candidates we don't already track."""
    from aria.signals import client as signals  # lazy — avoids import cycle

    wanted: list[str] = []
    for n in snapshot.narratives:
        for sym in narrative_rotation._candidates_from(n):
            if sym in config.ELIGIBLE_SYMBOLS and sym not in snapshot.token_quotes:
                wanted.append(sym)
    wanted = list(dict.fromkeys(wanted))[:10]  # bound the credit spend per cycle
    if wanted:
        extra = await signals.quotes_for(wanted)
        snapshot.token_quotes.update(extra)
        log.info("enriched quotes for candidates: %s", sorted(extra.keys()))


async def refine(
    decision: Decision, snapshot: MarketSnapshot, portfolio: PortfolioState
) -> Decision:
    if decision.action == "hold" and decision.mode != "preservation":
        return decision  # nothing to concretize

    if decision.mode == "narrative_rotation":
        if decision.action in ("buy",):
            await _enrich_candidate_quotes(snapshot)
            proposal = narrative_rotation.propose(
                snapshot, portfolio, preferred_token=decision.token_symbol
            )
            return _merge(decision, proposal)
        return decision  # sell/close_all pass through to safety as-is

    if decision.mode == "preservation":
        return _merge(decision, preservation.propose(portfolio))

    if decision.mode == "mean_reversion":
        return _merge(decision, mean_reversion.propose(snapshot, portfolio))

    return decision
