"""Shared data contracts. The Decision model is the contract between
brain -> safety -> execution: nothing acts on LLM output that hasn't validated here."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from aria import config

Regime = Literal["trending", "ranging", "high_risk"]
Mode = Literal["narrative_rotation", "mean_reversion", "preservation"]
Action = Literal["buy", "sell", "close_all", "hold"]


class Decision(BaseModel):
    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    regime: Regime
    mode: Mode
    action: Action
    token_symbol: Optional[str] = None   # required for buy/sell; must pass universe gates
    size_pct: float = Field(0.0, ge=0.0)
    stop_loss_pct: Optional[float] = None  # required for buy actions
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

    @field_validator("size_pct")
    @classmethod
    def size_within_cap(cls, v: float) -> float:
        if v > config.MAX_POSITION_PCT:
            raise ValueError(f"size_pct {v} exceeds MAX_POSITION_PCT {config.MAX_POSITION_PCT}")
        return v


class BrainOutput(BaseModel):
    """What the LLM is allowed to emit — a strict subset of Decision.
    cycle_id/timestamp are runtime concerns and never the model's to choose."""
    regime: Regime
    mode: Mode
    action: Action
    token_symbol: Optional[str] = None
    size_pct: float = Field(0.0, ge=0.0)
    stop_loss_pct: Optional[float] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

    def to_decision(self) -> Decision:
        return Decision(**self.model_dump())


def hold_decision(reason: str, regime: Regime = "high_risk") -> Decision:
    """Fail-safe default: anything ambiguous or broken becomes a logged hold."""
    return Decision(
        regime=regime,
        mode="preservation",
        action="hold",
        confidence=0.0,
        reasoning=reason,
    )


class Position(BaseModel):
    token_symbol: str
    amount: float
    entry_price_usd: float
    stop_loss_pct: Optional[float] = None
    opened_at: datetime


class PortfolioState(BaseModel):
    timestamp: datetime
    total_value_usd: float
    peak_value_usd: float          # high-water mark for drawdown computation
    positions: list[Position] = []
    stable_balance_usd: float = 0.0
    trades_today: int = 0

    @property
    def drawdown_pct(self) -> float:
        if self.peak_value_usd <= 0:
            return 0.0
        return max(0.0, (1 - self.total_value_usd / self.peak_value_usd) * 100)


class MarketSnapshot(BaseModel):
    """Raw-ish signals from CMC. Regime is NOT in here — the brain synthesizes it."""
    timestamp: datetime
    fear_greed_index: Optional[int] = None       # 0-100
    fear_greed_label: Optional[str] = None
    total_mcap_change_24h_pct: Optional[float] = None
    total_mcap_change_7d_pct: Optional[float] = None
    mcap_ta: dict = {}                            # market-cap SMA/EMA/MACD/RSI
    derivatives: dict = {}                        # open interest, funding, liquidations
    narratives: list[dict] = []                   # trending narratives + top tokens
    macro_events: list[dict] = []
    token_quotes: dict[str, dict] = {}            # symbol -> quote fields
    raw: dict = {}                                # full payloads for the audit log
