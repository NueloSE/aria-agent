"""Live Claude brain. One call per cycle: signals + portfolio in, BrainOutput out.

Hardening contract (docs/DESIGN.md): malformed, invalid, or failed LLM output NEVER
crashes the loop — every failure path returns a logged hold. The structured-output
schema constrains the response; Pydantic re-validates anyway (defense in depth).
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from anthropic import AsyncAnthropic

from aria import config
from aria.brain.prompt import (
    JUDGE_SYSTEM_PROMPT, SYSTEM_PROMPT, build_judge_message, build_user_message,
)
from aria.models import (
    BrainOutput, Decision, EntryJudgment, MarketSnapshot, PortfolioState, hold_decision,
)

log = logging.getLogger("aria.brain")

_client: Optional[AsyncAnthropic] = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def parse_brain_output(data: Any) -> Decision:
    """Pure function: raw model output (dict) -> validated Decision.
    Raises on anything invalid — caller converts to hold. Unit-test target."""
    output = BrainOutput.model_validate(data)
    return output.to_decision()


async def decide_live(
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    history: Optional[Sequence[dict]] = None,
) -> Decision:
    try:
        response = await _get_client().messages.parse(
            model=config.BRAIN_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(snapshot, portfolio, history)}],
            output_format=BrainOutput,
        )
    except Exception as exc:  # noqa: BLE001 — API/billing/network: hold, never crash
        log.error("brain API call failed: %s", exc)
        return hold_decision(f"brain API call failed: {type(exc).__name__}: {exc}")

    try:
        if response.parsed_output is None:
            raise ValueError(f"no parsed output (stop_reason={response.stop_reason})")
        decision = response.parsed_output.to_decision()
    except Exception as exc:  # noqa: BLE001 — malformed output: hold, never crash
        log.error("brain output invalid: %s", exc)
        return hold_decision(f"brain output invalid: {exc}")

    log.info("brain tokens in/out: %s/%s",
             response.usage.input_tokens, response.usage.output_tokens)
    return decision


def _reject(reason: str) -> EntryJudgment:
    """Fail-safe judgment: any failure/malformed output rejects the entry."""
    return EntryJudgment(approve=False, confidence=0.0, reasoning=reason)


async def judge_entry_live(
    candidate,
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    posture,
) -> EntryJudgment:
    """One focused Claude call to approve/reject a single deterministic entry candidate.
    Every failure path returns a reject — a missed entry is free, a bad one is not."""
    try:
        response = await _get_client().messages.parse(
            model=config.BRAIN_MODEL,
            max_tokens=1024,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": build_judge_message(candidate, snapshot, portfolio, posture)}],
            output_format=EntryJudgment,
        )
    except Exception as exc:  # noqa: BLE001 — API/billing/network: reject, never crash
        log.error("judge API call failed: %s", exc)
        return _reject(f"judge API call failed: {type(exc).__name__}: {exc}")

    try:
        if response.parsed_output is None:
            raise ValueError(f"no parsed output (stop_reason={response.stop_reason})")
        judgment = response.parsed_output
    except Exception as exc:  # noqa: BLE001 — malformed output: reject, never crash
        log.error("judge output invalid: %s", exc)
        return _reject(f"judge output invalid: {exc}")

    log.info("judge %s -> %s (conf %.2f) | tokens in/out: %s/%s",
             candidate.token_symbol, "APPROVE" if judgment.approve else "REJECT",
             judgment.confidence, response.usage.input_tokens, response.usage.output_tokens)
    return judgment
