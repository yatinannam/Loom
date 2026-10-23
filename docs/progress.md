# Progress Log

One entry per milestone: what was added, tests run with their results, decisions and
known issues. Newest entry last.

## 2026-10-23 — Design and plan

- Added `docs/brief.md` (original requirements), `docs/design.md` (approved design) and
  `docs/plan.md` (implementation plan, 15 tasks).

## 2026-10-23 — Task 1: scaffold, configuration, LLM provider

Added

- `backend/` uv project (Python 3.11): FastAPI, Pydantic, pydantic-settings, httpx,
  neo4j, chromadb, pypdf.
- `app/config.py`: all settings with defaults, read from environment and repository
  `.env`.
- `app/logging.py`: JSON log formatter; httpx request logging suppressed.
- `app/llm/provider.py`: `OpenAICompatibleLLM` for Groq or any OpenAI-compatible
  endpoint. Temperature 0, JSON mode, sliding-window request throttle, retries with
  `retry-after` and exponential backoff on 429, 5xx and transport errors, typed errors
  (`llm_not_configured`, `llm_rate_limited`, `llm_unavailable`, `llm_bad_response`).
- `app/llm/cache.py`: SQLite response cache keyed by SHA-256 of model, messages, JSON
  mode and max tokens. Cache hits are reported with `cached = true`.
- `docker-compose.yml` with Neo4j 5 Community (1 GB heap, 512 MB page cache, health
  check, persistent volume); `.env.example`.

Tests

- `uv run pytest tests/test_llm_provider.py`: 6 passed.

Decisions

- Cache lookup happens before the API key check, so cached results remain readable
  without a key. A cache miss without a key raises `llm_not_configured`.
