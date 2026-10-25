import json

import httpx
import pytest

from app.llm.cache import LLMCache
from app.llm.provider import LLMNotConfigured, LLMRateLimited, OpenAICompatibleLLM

MESSAGES = [{"role": "user", "content": "hello"}]


def ok_body(text="hi", prompt=5, completion=2):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


def make_llm(handler, api_key="k", cache=None, max_retries=2):
    return OpenAICompatibleLLM(
        base_url="https://llm.test/v1",
        api_key=api_key,
        timeout_s=5,
        max_rpm=1000,
        max_retries=max_retries,
        cache=cache,
        transport=httpx.MockTransport(handler),
    )


def test_complete_returns_text_and_usage():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body("hi", 5, 2))

    resp = make_llm(handler).complete(MESSAGES, model="m1")
    assert resp.text == "hi"
    assert resp.usage.prompt_tokens == 5
    assert resp.usage.completion_tokens == 2
    assert resp.usage.cached is False
    assert seen["url"] == "https://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["temperature"] == 0
    assert seen["body"]["model"] == "m1"


def test_missing_key_raises_not_configured():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ok_body())

    with pytest.raises(LLMNotConfigured):
        make_llm(handler, api_key="").complete(MESSAGES, model="m1")
    assert calls == []


def test_429_retries_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={})
        return httpx.Response(200, json=ok_body("second"))

    resp = make_llm(handler).complete(MESSAGES, model="m1")
    assert resp.text == "second"
    assert len(calls) == 2


def test_429_exhausted_raises_rate_limited():
    def handler(request):
        return httpx.Response(429, headers={"retry-after": "0"}, json={})

    with pytest.raises(LLMRateLimited):
        make_llm(handler, max_retries=1).complete(MESSAGES, model="m1")


def test_cache_hit_skips_http_and_marks_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ok_body("cached text"))

    llm = make_llm(handler, cache=LLMCache(tmp_path / "cache.db"))
    first = llm.complete(MESSAGES, model="m1")
    second = llm.complete(MESSAGES, model="m1")
    assert len(calls) == 1
    assert first.usage.cached is False
    assert second.usage.cached is True
    assert second.text == "cached text"
    assert second.usage.prompt_tokens == 5


def test_json_mode_sets_response_format():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body("{}"))

    make_llm(handler).complete(MESSAGES, model="m1", json_mode=True)
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_json_validate_failed_400_raises_invalid_json():
    from app.llm.provider import LLMBadResponse, LLMInvalidJSON

    def handler(request):
        return httpx.Response(400, json={"error": {"message": "Failed to generate JSON", "code": "json_validate_failed"}})

    with pytest.raises(LLMInvalidJSON) as exc:
        make_llm(handler).complete(MESSAGES, model="m1", json_mode=True)
    assert isinstance(exc.value, LLMBadResponse)


def test_other_400_is_not_invalid_json():
    from app.llm.provider import LLMBadResponse, LLMInvalidJSON

    def handler(request):
        return httpx.Response(401, json={"error": {"message": "Invalid API Key", "code": "invalid_api_key"}})

    with pytest.raises(LLMBadResponse) as exc:
        make_llm(handler).complete(MESSAGES, model="m1")
    assert not isinstance(exc.value, LLMInvalidJSON)
