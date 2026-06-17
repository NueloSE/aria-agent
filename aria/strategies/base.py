"""Strategy contracts. Strategies PROPOSE; they never execute, never sign,
never talk to the network. Pure functions over the snapshot + portfolio."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class Proposal(BaseModel):
    action: Literal["buy", "sell", "close_all", "hold"]
    token_symbol: Optional[str] = None
    size_pct: float = 0.0
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None  # take-profit; must clear the fee gate
    rationale: str                      # gate-by-gate audit trail, logged verbatim


def hold_proposal(rationale: str) -> Proposal:
    return Proposal(action="hold", rationale=rationale)
