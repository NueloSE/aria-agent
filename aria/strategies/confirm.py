"""Per-candidate technical confirmation, shared by mean-reversion and breakout.

The deterministic gate narrows the universe to ONE best candidate using cheap
%-change fields. Before we commit (and before we spend an LLM judge call), we pull
real per-token technical analysis for just that one token (get_crypto_technical_analysis,
1 credit) and confirm:

  - mean-reversion: RSI-14 confirms genuine OVERSOLD (not merely "down").
  - breakout:       RSI-14 confirms NOT OVERBOUGHT (room to run).
  - both:           Fibonacci levels set a structure-aware target (nearest resistance
                    above) and stop (just below the nearest support).

Pure functions over a parsed TA dict — no network here. Fail-safe by construction:
empty/missing TA => the gate passes and target/stop fall back to the strategy defaults.
"""
from __future__ import annotations

from aria import config
from aria.signals.parsing import parse_float, parse_usd
from aria.strategies.base import Proposal


def parse_ta(ta: dict) -> dict:
    """Raw get_crypto_technical_analysis payload -> the few numbers we use."""
    rsi = ta.get("rsi", {}) or {}
    macd = ta.get("macd", {}) or {}
    fib = ta.get("fibonacciLevels", {}) or {}
    ma = ta.get("moving_averages", {}) or {}
    retr = fib.get("retracementLevels", {}) or {}
    ext = fib.get("extensionLevels", {}) or {}
    levels = [v for raw in list(retr.values()) + list(ext.values())
              if (v := parse_usd(raw)) is not None]
    return {
        "rsi14": parse_float(rsi.get("rsi14")),
        "rsi21": parse_float(rsi.get("rsi21")),
        "macd_hist": parse_float(macd.get("histogram")),
        "swing_low": parse_usd(fib.get("swingLow")),
        "swing_high": parse_usd(fib.get("swingHigh")),
        "sma7": parse_usd(ma.get("simple_moving_average_7_day")),
        "pivot": parse_usd(ta.get("pivotPoint")),
        "resistance_levels": levels,
    }


def _target_pct(price: float, ta: dict) -> "float | None":
    """Nearest Fibonacci level above price that clears the fee gate (bounce/extension target)."""
    if not price or price <= 0:
        return None
    floor = max(config.round_trip_cost_pct() * config.MIN_EDGE_MULTIPLE,
                config.MR_FIB_TARGET_MIN_PCT)
    for lvl in sorted(l for l in ta["resistance_levels"] if l > price):
        pct = (lvl / price - 1.0) * 100.0
        if floor <= pct <= config.MR_FIB_TARGET_MAX_PCT:
            return round(pct, 2)
    return None


def _stop_pct(price: float, ta: dict, supports: list) -> "float | None":
    """Stop just below the nearest support (swing low / pivot / SMA7) below price."""
    if not price or price <= 0:
        return None
    below = [s for s in supports if s and 0 < s < price]
    if not below:
        return None
    pct = (1.0 - (max(below) * 0.99) / price) * 100.0
    if config.MR_FIB_STOP_MIN_PCT <= pct <= config.MR_FIB_STOP_MAX_PCT:
        return round(pct, 2)
    return None


def _apply_levels(proposal: Proposal, ta: dict, price: "float | None",
                  supports: list, note: str) -> Proposal:
    target = (_target_pct(price, ta) if price else None) or proposal.target_pct
    stop = (_stop_pct(price, ta, supports) if price else None) or proposal.stop_loss_pct
    if target != proposal.target_pct or stop != proposal.stop_loss_pct:
        note += f"; fib target {target:.1f}% / stop {stop:.1f}%"
    return proposal.model_copy(update={
        "target_pct": target, "stop_loss_pct": stop,
        "rationale": f"{proposal.rationale} | confirm: {note}",
    })


def confirm_candidate(proposal: Proposal, ta: dict, price: "float | None"
                      ) -> "tuple[bool, str, Proposal]":
    """Mean-reversion gate: require genuine OVERSOLD. Returns (ok, reason, proposal)."""
    rsi14 = ta.get("rsi14")
    if rsi14 is not None and rsi14 > config.MR_RSI_MAX:
        return False, f"RSI-14 {rsi14:.0f} > {config.MR_RSI_MAX:.0f} — not oversold", proposal
    note = f"RSI-14 {rsi14:.0f} oversold" if rsi14 is not None else "RSI n/a"
    return True, note, _apply_levels(proposal, ta, price, [ta.get("swing_low")], note)


def confirm_breakout(proposal: Proposal, ta: dict, price: "float | None"
                     ) -> "tuple[bool, str, Proposal]":
    """Breakout gate: require NOT OVERBOUGHT (room to run). Returns (ok, reason, proposal)."""
    rsi14 = ta.get("rsi14")
    if rsi14 is not None and rsi14 > config.BO_RSI_MAX:
        return False, f"RSI-14 {rsi14:.0f} > {config.BO_RSI_MAX:.0f} — overbought, no room", proposal
    note = f"RSI-14 {rsi14:.0f} not overbought" if rsi14 is not None else "RSI n/a"
    supports = [ta.get("pivot"), ta.get("sma7"), ta.get("swing_low")]
    return True, note, _apply_levels(proposal, ta, price, supports, note)
