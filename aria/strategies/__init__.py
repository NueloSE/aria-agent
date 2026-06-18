"""Strategies PROPOSE trades; they never execute. One module per mode.

refine() is the router: the brain picks regime/mode and suggests; the mode's
strategy turns that into a concrete, gate-checked proposal. The brain can never
produce a trade the gates didn't independently approve."""
from __future__ import annotations

import logging

from aria import config
from aria.models import Decision, MarketSnapshot, PortfolioState
from aria.strategies import breakout, mean_reversion, narrative_rotation, preservation
from aria.strategies.base import Proposal, hold_proposal

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
        target_pct=proposal.target_pct,
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


async def scan_entries(
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    allow_narrative: bool = False,
    skip: "set[str] | None" = None,
) -> "tuple[Proposal, str | None]":
    """Run the deterministic entry gates to surface ONE candidate (or hold).

    This is the fast loop's entry hunter — pure gate logic, NO LLM. Mean-reversion
    (counter-trend, works in any regime, zero extra credits) is scanned every tick;
    narrative-rotation (needs a trend, costs candidate-quote enrichment) only when the
    caller permits it (typically right after a macro refresh). `skip` excludes tokens in
    cooldown (just-exited or judge-rejected) so the gate returns the best NON-cooled
    candidate. Returns the Proposal and its mode ('mean_reversion' | 'narrative_rotation' | None)."""
    skip = skip or set()
    mr = mean_reversion.propose(snapshot, portfolio, skip=skip)
    if mr.action == "buy":
        return mr, "mean_reversion"

    # Breakout/momentum — fires in recovering/trending markets MR misses (more coverage).
    if config.BO_ENABLED:
        bo = breakout.propose(snapshot, portfolio, skip=skip)
        if bo.action == "buy":
            return bo, "breakout"

    if allow_narrative:
        await _enrich_candidate_quotes(snapshot)
        nr = narrative_rotation.propose(snapshot, portfolio, skip=skip)
        if nr.action == "buy":
            return nr, "narrative_rotation"

    return hold_proposal("no entry setup (scanned mean-reversion"
                         + (" + narrative-rotation" if allow_narrative else "") + ")"), None


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
        if decision.action == "buy":
            return _merge(decision, mean_reversion.propose(snapshot, portfolio))
        return decision  # sell/close_all/hold pass through

    return decision
