"""Deterministic test doubles. Never imported by application code."""

import hashlib
import math
import re

from app.llm.provider import LLMResponse, LLMUsage


class HashEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    dims = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                vec[h % self.dims] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FakeLLM:
    """Returns the canned response whose key occurs in the last user message.

    `responses` is a list of (key substring, response text or Exception). Raises
    AssertionError when nothing matches so tests fail loudly on unexpected prompts.
    """

    def __init__(self, responses: list[tuple[str, object]]):
        self.responses = responses
        self.calls: list[dict] = []

    def complete(self, messages, *, model, json_mode=False, max_tokens=1024):
        prompt = messages[-1]["content"]
        self.calls.append({"model": model, "messages": messages, "json_mode": json_mode})
        for key, response in self.responses:
            if key in prompt:
                if isinstance(response, Exception):
                    raise response
                return LLMResponse(
                    text=response,
                    usage=LLMUsage(model=model, prompt_tokens=len(prompt) // 4, completion_tokens=10,
                                   latency_ms=1.0, cached=False),
                )
        raise AssertionError(f"FakeLLM has no response for prompt: {prompt[:200]!r}")
