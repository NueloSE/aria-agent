"""Execution layer tests — pure functions + envelope parsing. No subprocesses,
no network, no real swaps (those are the funded dust-trade verification)."""
from __future__ import annotations

import pytest

from aria import config
from aria.execution import check_quote, parse_amount
from aria.execution.twak_client import TwakError, parse_tool_result


class TestParseToolResult:
    def test_json_payload_unwrapped(self):
        msg = {"result": {"content": [{"type": "text", "text": '{"success": true}'}]}}
        assert parse_tool_result(msg) == {"success": True}

    def test_plain_text_passthrough(self):
        msg = {"result": {"content": [{"type": "text", "text": "ok"}]}}
        assert parse_tool_result(msg) == "ok"

    def test_tool_error_raises(self):
        msg = {"result": {"isError": True, "content": [
            {"type": "text", "text": '{"code":"VALIDATION_ERROR","message":"Required"}'}]}}
        with pytest.raises(TwakError, match="VALIDATION_ERROR"):
            parse_tool_result(msg)

    def test_rpc_error_raises(self):
        with pytest.raises(TwakError, match="rpc error"):
            parse_tool_result({"error": {"code": -32601, "message": "no such method"}})

    def test_garbage_envelope_raises(self):
        with pytest.raises(TwakError, match="unexpected envelope"):
            parse_tool_result({"result": {"content": []}})


class TestQuoteGate:
    def test_clean_quote_passes(self):
        q = {"success": True, "input": "10 USDT", "output": "0.0059 ETH",
             "provider": "LiquidMesh", "priceImpact": "0", "steps": 1}
        assert check_quote(q) is None

    def test_high_impact_rejected(self):
        q = {"success": True, "priceImpact": str(config.MAX_PRICE_IMPACT_PCT + 1)}
        assert "price impact" in check_quote(q)

    def test_boundary_impact_passes(self):
        q = {"success": True, "priceImpact": str(config.MAX_PRICE_IMPACT_PCT)}
        assert check_quote(q) is None

    def test_failed_quote_rejected(self):
        assert "quote failed" in check_quote({"success": False})

    def test_empty_quote_rejected(self):
        assert check_quote({}) is not None

    def test_unparseable_impact_rejected(self):
        q = {"success": True, "priceImpact": "lol"}
        assert "unparseable" in check_quote(q)

    def test_percent_suffix_tolerated(self):
        q = {"success": True, "priceImpact": "1.2%"}
        assert check_quote(q) is None


class TestParseAmount:
    def test_amount_with_symbol(self):
        assert parse_amount("0.005937219560528063 ETH") == (0.005937219560528063, "ETH")

    def test_amount_bare(self):
        assert parse_amount("10.5") == (10.5, "")

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_amount("not a number")
