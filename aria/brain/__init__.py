"""LLM reasoning brain. Input: MarketSnapshot + PortfolioState. Output: validated Decision.
Malformed output never crashes the loop — it becomes a logged hold."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from aria import config
from aria.models import (
    Decision, EntryJudgment, MarketSnapshot, PortfolioState, hold_decision,
)

if TYPE_CHECKING:
    from aria.regime import RiskPosture
    from aria.strategies.base import Proposal


async def judge_entry(
    candidate: "Proposal",
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    posture: "RiskPosture",
) -> EntryJudgment:
    """The LLM's verdict on ONE deterministic entry candidate (event-driven — called
    only when a gate found a real setup, never on a fixed clock). Approves/rejects on
    macro-regime grounds; cannot pick a different token."""
    if config.BRAIN_MODE == "mock":
        return _mock_judge(candidate, snapshot, posture)
    from aria.brain.live import judge_entry_live  # lazy: no client init in mock mode
    return await judge_entry_live(candidate, snapshot, portfolio, posture)


def _mock_judge(candidate: "Proposal", snapshot: MarketSnapshot,
                posture: "RiskPosture") -> EntryJudgment:
    """Deterministic stand-in for the LLM judge (offline tests). Approves the gate's
    setup unless sentiment is in genuine capitulation; mirrors the live judge's shape."""
    fg = snapshot.fear_greed_index
    if fg is not None and fg <= config.POSTURE_EXTREME_FEAR:
        return EntryJudgment(approve=False, confidence=0.9,
                             reasoning=f"mock judge: F&G={fg} extreme fear — reject new risk")
    conf = 0.72 if posture.label in ("risk_on", "neutral") else 0.65
    return EntryJudgment(approve=True, confidence=conf, size_pct=candidate.size_pct,
                         reasoning=f"mock judge: approve {candidate.token_symbol} "
                                   f"(posture={posture.label})")


async def decide(
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    history: Optional[Sequence[dict]] = None,
) -> Decision:
    if config.BRAIN_MODE == "mock":
        return _mock_decide(snapshot, portfolio)
    from aria.brain.live import decide_live  # lazy: avoids client init in mock mode
    return await decide_live(snapshot, portfolio, history)


def _mock_decide(snapshot: MarketSnapshot, portfolio: PortfolioState) -> Decision:
    """Deterministic rule-of-thumb brain for offline testing. NOT the real logic —
    just plausible-enough output to exercise safety/execution/logging paths."""
    fg = snapshot.fear_greed_index
    if fg is None:
        return hold_decision("mock brain: no fear/greed signal -> hold")
    if fg <= 25:
        return Decision(
            regime="high_risk",
            mode="preservation",
            action="hold" if not portfolio.positions else "close_all",
            confidence=0.9,
            reasoning=f"mock brain: F&G={fg} ({snapshot.fear_greed_label}) -> preservation",
        )
    if fg >= 60:
        # Propose a buy with no token preference — the narrative-rotation gates
        # pick the concrete token (and can still reject the whole idea).
        return Decision(
            regime="trending",
            mode="narrative_rotation",
            action="buy",
            token_symbol=None,
            size_pct=10.0,
            stop_loss_pct=6.0,
            confidence=0.72,
            reasoning=f"mock brain: F&G={fg} ({snapshot.fear_greed_label}) -> trending; "
                      "delegating token selection to narrative gates",
        )
    # 26-59: ranging — try the counter-trend mean-reversion play. The gate finds
    # an oversold-reclaim setup or returns hold; either way we're not idle.
    return Decision(
        regime="ranging",
        mode="mean_reversion",
        action="buy",
        token_symbol=None,
        size_pct=config.MR_SIZE_PCT,
        confidence=0.65,
        reasoning=f"mock brain: F&G={fg} ranging -> scan for oversold-reclaim "
                  "(mean-reversion gate decides)",
    )
