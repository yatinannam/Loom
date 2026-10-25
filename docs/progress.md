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

## 2026-10-23 — Task 2: registry

Added

- `app/registry.py`: SQLite registry (WAL) for documents, extraction errors, activity
  feed, evaluation runs and per-question evaluation records. `DocumentRow` Pydantic
  model. Connections are opened and closed per call.
- `.gitattributes` normalizing line endings to LF.

Tests

- `uv run pytest`: 13 passed (7 registry, 6 provider).

## 2026-10-23 — Task 3: parsing and chunking

Added

- `app/ingestion/parsing.py`: upload validation (extension allow-list `.pdf .txt .md`,
  size limit, empty file, PDF magic bytes), content-hash document ids (16 hex chars of
  SHA-256), text extraction per PDF page with pypdf, UTF-8 text for TXT and Markdown.
  Files without any text raise `NoExtractableText`.
- `app/ingestion/chunking.py`: character windows (`CHUNK_SIZE`, `CHUNK_OVERLAP`)
  breaking at the last paragraph or sentence boundary in the final 30% of the window;
  the next chunk starts on a word boundary inside the overlap. Chunks never span PDF
  pages. `ChunkRecord` in `app/models.py`.
- `tests/pdf_fixture.py`: builds minimal text-layer PDFs in tests.

Tests

- `uv run pytest`: 27 passed.

## 2026-10-25 — Task 4: vector store

Added

- `app/vector/store.py`: `ChromaVectorStore` over two cosine collections
  (`{prefix}-chunks`, `{prefix}-entities`). Embeddings are computed by an `Embedder` and
  passed to Chroma explicitly. `make_embedder`: `all-MiniLM-L6-v2` uses Chroma's bundled
  ONNX model; any other name loads sentence-transformers (optional extra `st`).
  `model_slug` gives the collection prefix so changing the model never mixes vector
  dimensions. Similarity score is `1 - cosine distance`.
- `tests/fakes.py`: `HashEmbedder` (deterministic bag-of-words hashing) and `FakeLLM`
  (canned responses keyed by prompt substring; fails loudly on unknown prompts).

Tests

- `uv run pytest`: 35 passed.

Decisions

- Chroma metadata cannot store null, so a missing page number is stored as `-1` and
  mapped back to `None`.
- The real ONNX embedder was not exercised in this task; it downloads the model
  (about 80 MB) on first use and is covered by the live smoke test in Task 9.

## 2026-10-25 — Task 5: extraction and graph stores

Added

- `app/extraction/schema.py`: Pydantic schema for extraction output. Entity types are
  an allow-list (unknown types become `OTHER`); relation types are coerced to
  `UPPER_SNAKE_CASE`; confidence is clamped to [0, 1].
- `app/extraction/normalize.py`: name normalization (NFKC, lowercase, punctuation to
  space, collapsed whitespace, leading "the" removed), slug entity ids, and the evidence
  support check (substring after normalization, or 80% token overlap with one sentence).
- `app/extraction/extractor.py`: extraction prompt (JSON mode), validation that drops
  invalid entities, relations with unknown endpoints, self-relations and relations whose
  evidence is not in the chunk, each with a warning. One retry on unparseable output.
- `app/graph/store.py`: `GraphStore` protocol, `Entity`, `Relation`, `Mention`.
- `app/graph/memory_store.py`: in-process store with the same semantics (tests).
- `app/graph/neo4j_store.py`: Neo4j store. Unique constraints on `Entity.id` and
  `Chunk.id`; `(:Entity)-[:MENTIONED_IN]->(:Chunk)`; one `RELATES {type}` edge per
  (source, type, target) with parallel provenance lists (`chunk_ids`, `document_ids`,
  `evidence`). Document removal strips provenance, deletes empty edges, the document's
  chunk nodes and orphaned entities in one transaction.

Tests

- `uv run pytest`: 62 passed. Neo4j-backed store tests are skipped unless
  `NEO4J_TEST_URI` is set; not yet run (Docker Desktop not running).

Decisions

- Entity type: the first non-`OTHER` type assigned is kept (simpler than the
  most-frequent rule in the design).
