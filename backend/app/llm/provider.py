"""OpenAI-compatible chat completion client (Groq by default) with throttling,
retries and a disk cache."""

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Protocol

import httpx

from app.llm.cache import LLMCache

log = logging.getLogger(__name__)


class LLMError(Exception):
    code = "llm_error"


class LLMNotConfigured(LLMError):
    code = "llm_not_configured"


class LLMRateLimited(LLMError):
    code = "llm_rate_limited"


class LLMUnavailable(LLMError):
    code = "llm_unavailable"


class LLMBadResponse(LLMError):
    code = "llm_bad_response"


@dataclass
class LLMUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cached: bool


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage


class LLMProvider(Protocol):
    def complete(
        self, messages: list[dict], *, model: str, json_mode: bool = False, max_tokens: int = 1024
    ) -> LLMResponse: ...


class _RateLimiter:
    """Sliding 60 second window shared by all threads using one client."""

    def __init__(self, max_rpm: int):
        self.max_rpm = max_rpm
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.max_rpm:
                    self._calls.append(now)
                    return
                wait = 60 - (now - self._calls[0])
            time.sleep(max(wait, 0.05))


class OpenAICompatibleLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float,
        max_rpm: int,
        max_retries: int,
        cache: LLMCache | None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries
        self.cache = cache
        self._limiter = _RateLimiter(max_rpm)
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(
        self, messages: list[dict], *, model: str, json_mode: bool = False, max_tokens: int = 1024
    ) -> LLMResponse:
        key = LLMCache.make_key(model, messages, json_mode, max_tokens)
        if self.cache:
            hit = self.cache.get(key)
            if hit:
                usage = LLMUsage(**{**hit["usage"], "cached": True, "latency_ms": 0.0})
                return LLMResponse(text=hit["text"], usage=usage)

        if not self.api_key:
            raise LLMNotConfigured("LLM_API_KEY is not set; ingestion and querying need an LLM provider key")

        body: dict = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        data = self._post(body)
        latency_ms = (time.perf_counter() - start) * 1000

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponse(f"unexpected completion payload: {exc}") from exc
        raw_usage = data.get("usage") or {}
        usage = LLMUsage(
            model=model,
            prompt_tokens=int(raw_usage.get("prompt_tokens", 0)),
            completion_tokens=int(raw_usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            cached=False,
        )
        if self.cache:
            self.cache.set(key, {"text": text, "usage": asdict(usage)})
        return LLMResponse(text=text, usage=usage)

    def _post(self, body: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error = ""
        for attempt in range(self.max_retries + 1):
            self._limiter.acquire()
            try:
                resp = self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                resp = None
            if resp is not None and resp.status_code == 200:
                return resp.json()
            if resp is not None and resp.status_code not in (429,) and resp.status_code < 500:
                raise LLMBadResponse(f"provider returned HTTP {resp.status_code}: {resp.text[:300]}")
            if attempt == self.max_retries:
                break
            retry_after = _retry_after(resp)
            delay = min(retry_after if retry_after is not None else 2**attempt, 30)
            if resp is not None:
                last_error = f"HTTP {resp.status_code}"
            log.warning("llm request failed (%s), retrying in %.1fs", last_error, delay)
            time.sleep(delay)
        if resp is not None and resp.status_code == 429:
            raise LLMRateLimited(f"provider rate limit reached after {self.max_retries + 1} attempts: {resp.text[:300]}")
        raise LLMUnavailable(f"provider unavailable: {last_error}")


def _retry_after(resp: httpx.Response | None) -> float | None:
    if resp is None:
        return None
    value = resp.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
