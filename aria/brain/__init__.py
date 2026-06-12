"""LLM reasoning brain. Input: MarketSnapshot + PortfolioState. Output: validated Decision.
Malformed output never crashes the loop — it becomes a logged hold."""
from __future__ import annotations

from typing import Optional, Sequence

from aria import config
from aria.models import Decision, MarketSnapshot, PortfolioState, hold_decision


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
        return Decision(
            regime="trending",
            mode="narrative_rotation",
            action="hold",  # strategies propose actual entries from Stage 5
            confidence=0.7,
            reasoning=f"mock brain: F&G={fg} -> trending; entry proposals land in Stage 5",
        )
    return Decision(
        regime="ranging",
        mode="preservation",
        action="hold",
        confidence=0.6,
        reasoning=f"mock brain: F&G={fg} mid-range -> no edge, hold",
    )
