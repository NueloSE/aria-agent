"""Per-candidate technical confirmation: RSI gates + Fibonacci target/stop."""
from __future__ import annotations

import pytest

from aria import config
from aria.strategies.base import Proposal
from aria.strategies.confirm import (
    _stop_pct, _target_pct, confirm_breakout, confirm_candidate, parse_ta,
)

# mirrors a real get_crypto_technical_analysis payload (comma-number strings)
TA_RAW = {
    "macd": {"histogram": "25.12"},
    "rsi": {"rsi7": "50.09", "rsi14": "41.48", "rsi21": "39.61"},
    "moving_averages": {"simple_moving_average_7_day": "1,560.00"},
    "pivotPoint": "1,559.96",
    "fibonacciLevels": {
        "swingHigh": "2,154.22", "swingLow": "1,506.51",
        "retracementLevels": {"50.0%": "1,830.36", "23.6%": "2,001.36",
                              "38.2%": "1,906.79", "78.6%": "1,645.12", "61.8%": "1,753.93"},
        "extensionLevels": {"161.8%": "2,554.51", "127.2%": "2,330.40"},
    },
}


def cand(target=7.0, stop=5.0) -> Proposal:
    return Proposal(action="buy", token_symbol="ETH", size_pct=10.0,
                    stop_loss_pct=stop, target_pct=target, rationale="setup")


class TestParse:
    def test_extracts_fields_incl_extensions(self):
        p = parse_ta(TA_RAW)
        assert p["rsi14"] == pytest.approx(41.48)
        assert p["swing_low"] == pytest.approx(1506.51)
        assert p["sma7"] == pytest.approx(1560.0)
        assert 2554.51 in [round(x, 2) for x in p["resistance_levels"]]  # extension included

    def test_empty_is_safe(self):
        p = parse_ta({})
        assert p["rsi14"] is None and p["resistance_levels"] == []


class TestLevels:
    def test_target_is_nearest_qualifying_level_above(self):
        ta = parse_ta(TA_RAW)
        assert _target_pct(1650.0, ta) == pytest.approx(6.3, abs=0.2)  # 1753.93

    def test_target_skips_too_close_and_too_far(self):
        ta = {"resistance_levels": [101.0, 500.0]}  # +1% (below floor) / +400% (above max)
        assert _target_pct(100.0, ta) is None

    def test_stop_below_nearest_support_in_band(self):
        ta = parse_ta(TA_RAW)
        # supports below 1600: swing_low 1506.51 -> ~6.8%
        assert _stop_pct(1600.0, ta, [ta["swing_low"]]) == pytest.approx(6.8, abs=0.3)

    def test_stop_none_when_no_support_below(self):
        assert _stop_pct(1400.0, parse_ta(TA_RAW), [1506.51]) is None


class TestConfirmMR:
    def test_rejects_not_oversold(self, monkeypatch):
        monkeypatch.setattr(config, "MR_RSI_MAX", 45.0)
        ta = parse_ta({**TA_RAW, "rsi": {"rsi14": "58.0"}})
        ok, reason, _ = confirm_candidate(cand(), ta, 1600.0)
        assert not ok and "not oversold" in reason

    def test_oversold_passes_and_upgrades_levels(self):
        ok, _r, c = confirm_candidate(cand(), parse_ta(TA_RAW), 1600.0)
        assert ok and (c.target_pct != 7.0 or c.stop_loss_pct != 5.0)
        assert "confirm:" in c.rationale

    def test_missing_ta_fail_safe_keeps_defaults(self):
        ok, _r, c = confirm_candidate(cand(), parse_ta({}), None)
        assert ok and c.target_pct == 7.0 and c.stop_loss_pct == 5.0


class TestConfirmBreakout:
    def test_rejects_overbought(self, monkeypatch):
        monkeypatch.setattr(config, "BO_RSI_MAX", 70.0)
        ta = parse_ta({**TA_RAW, "rsi": {"rsi14": "78.0"}})
        ok, reason, _ = confirm_breakout(cand(), ta, 1600.0)
        assert not ok and "overbought" in reason

    def test_not_overbought_passes(self):
        ok, _r, c = confirm_breakout(cand(), parse_ta(TA_RAW), 1600.0)
        assert ok and "not overbought" in c.rationale
