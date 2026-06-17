"""CMC client resilience: transient failures retry in-place; real errors raise."""
from __future__ import annotations

import json

import httpx
import pytest

from aria import config
from aria.signals.cmc_client import CMCClient, SignalError, _is_transient


def ok_msg(payload) -> dict:
    return {"result": {"content": [{"text": json.dumps(payload)}]}}


def err_msg(detail: str) -> dict:
    return {"result": {"isError": True, "content": [{"type": "text", "text": detail}]}}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_RETRY_BACKOFF_S", 0.0)  # no sleeps in tests
    monkeypatch.setattr(config, "SIGNAL_RETRY_ATTEMPTS", 3)
    c = CMCClient(api_key="test", url="http://unused")
    c._initialized = True  # skip the network handshake
    return c


class TestIsTransient:
    def test_500_is_transient(self):
        assert _is_transient('{"error":{"code":500,"message":"internal server error"}}')

    def test_rate_limit_and_5xx(self):
        assert _is_transient("429 too many requests")
        assert _is_transient("503 service unavailable")

    def test_bad_request_not_transient(self):
        assert not _is_transient('{"error":{"code":400,"message":"bad symbol"}}')


class TestRetry:
    async def test_transient_500_then_success(self, client, monkeypatch):
        calls = {"n": 0}
        async def fake_post(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return err_msg('{"error":{"code":500,"message":"internal server error"}}')
            return ok_msg({"price": 1.23})
        monkeypatch.setattr(client, "_post", fake_post)
        out = await client.call("get_crypto_quotes_latest")
        assert out == {"price": 1.23}
        assert calls["n"] == 2  # retried once, then succeeded

    async def test_transport_blip_then_success(self, client, monkeypatch):
        calls = {"n": 0}
        async def fake_post(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("name resolution failed")
            return ok_msg({"ok": True})
        monkeypatch.setattr(client, "_post", fake_post)
        assert await client.call("x") == {"ok": True}
        assert calls["n"] == 2

    async def test_exhausts_retries_then_raises(self, client, monkeypatch):
        async def always_500(payload):
            return err_msg('{"error":{"code":500,"message":"internal server error"}}')
        monkeypatch.setattr(client, "_post", always_500)
        with pytest.raises(SignalError, match="tool error"):
            await client.call("x")

    async def test_nontransient_error_raises_immediately(self, client, monkeypatch):
        calls = {"n": 0}
        async def bad_request(payload):
            calls["n"] += 1
            return err_msg('{"error":{"code":400,"message":"bad symbol"}}')
        monkeypatch.setattr(client, "_post", bad_request)
        with pytest.raises(SignalError, match="tool error"):
            await client.call("x")
        assert calls["n"] == 1  # no retry on a real (non-transient) error
