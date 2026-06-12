"""Mean reversion — DISABLED (MR_ENABLED=False).

Rationale (see docs/DESIGN.md): scoring applies simulated transaction costs
(unconfirmed ~1.5%/round trip). A 3% entry band + 2.5% stop has no edge after
costs. Revisit ONLY if the official cost model makes the math work."""
from __future__ import annotations

from aria.models import MarketSnapshot, PortfolioState
from aria.strategies.base import Proposal, hold_proposal


def propose(snapshot: MarketSnapshot, portfolio: PortfolioState) -> Proposal:
    return hold_proposal("mean_reversion disabled pending official cost model")
