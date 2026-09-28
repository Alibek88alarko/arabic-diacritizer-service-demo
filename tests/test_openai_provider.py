"""The provider layer against a fake OpenAI-compatible server (httpx MockTransport, no network)."""
import json

import httpx
import pytest

from diacritizer.providers import OpenAICompatibleProvider, Router, StubProvider

TEXT = "كتب"
FULL = "كَتَبَ"


def fake_server(script):
    """script: list of responses per call; each item is (status, body_dict) or an exception."""
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), calls


def ok_body(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"total_tokens": 12}}


def make(script, retries=1):
    transport, calls = fake_server(script)
    p = OpenAICompatibleProvider("https://llm.example/v1", "key", "model-x", retries=retries, transport=transport)
    return p, calls


def test_parses_chat_completion_and_sends_expected_payload():
    p, calls = make([(200, ok_body(FULL))])
    assert p.diacritize(TEXT) == FULL
    assert calls[0]["model"] == "model-x" and calls[0]["messages"][1]["content"] == TEXT
    assert calls[0]["temperature"] == 0


def test_retries_once_on_5xx_then_succeeds():
    p, calls = make([(503, {"error": "busy"}), (200, ok_body(FULL))], retries=1)
    assert p.diacritize(TEXT) == FULL and len(calls) == 2


def test_gives_up_after_retry_budget():
    p, calls = make([(500, {"error": "down"})], retries=2)
    with pytest.raises(RuntimeError, match="gave up after 3"):
        p.diacritize(TEXT)
    assert len(calls) == 3


def test_4xx_is_not_retried():
    p, calls = make([(401, {"error": "bad key"})], retries=3)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        p.diacritize(TEXT)
    assert len(calls) == 1


def test_transport_error_is_retried():
    p, calls = make([httpx.ConnectError("refused"), (200, ok_body(FULL))], retries=1)
    assert p.diacritize(TEXT) == FULL


def test_router_falls_back_when_model_rewrites_the_text():
    p, _ = make([(200, ok_body("كَتَتَ"))])   # last letter changed
    r = Router([p, StubProvider()], timeout_s=1, max_chars=100, daily_char_budget=1000).run(TEXT)
    assert r.provider == "stub" and "rejected by validator" in r.attempts[0]
