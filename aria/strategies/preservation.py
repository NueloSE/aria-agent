"""Capital preservation: get to stables and stay there — but never fully idle
(any hour starting under $1 in-scope scores 0%; USDT is on the eligible list,
so holding stables satisfies the in-scope requirement)."""
from __future__ import annotations

from aria.models import PortfolioState
from aria.strategies.base import Proposal, hold_proposal


def propose(portfolio: PortfolioState) -> Proposal:
    if portfolio.positions:
        return Proposal(
            action="close_all",
            rationale=f"preservation: closing {len(portfolio.positions)} position(s) to stables",
        )
    return hold_proposal("preservation: already in stables, holding")
