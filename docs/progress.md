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

## 2026-10-25 — Task 6: entity resolution and ingestion pipeline

Added

- `app/graph/resolution.py`: `EntityResolver`. Ingestion: exact normalized name or alias
  match, then difflib ratio >= 0.92 on the primary name; otherwise a new node. Query:
  exact (1.0), alias (0.95), fuzzy >= 0.85, embedding nearest neighbor above
  `ENTITY_MIN_SCORE`, plus a whole-word scan of the question for known names and aliases
  (0.9, keys of 3+ characters). Results deduplicated per entity, best score kept.
- `app/ingestion/pipeline.py`: `IngestionService.add_file` (validate, content-hash id,
  store under `data/runtime/uploads/`, registry row) and `ingest` (remove previous
  contribution, parse, chunk, embed, extract per chunk, resolve, upsert entities,
  relations and provenance, index entity names, recompute degrees, record counts).
  Any failure removes the partial contribution and marks the document `failed` with
  `code: message`. Extraction warnings are stored as extraction errors.
- `data/demo/`: the three smoke-test documents.
- `tests/fixtures/demo_llm.py`: canned extraction responses for the demo corpus.
- `tests/conftest.py`: test environment factory (ephemeral Chroma, in-memory graph,
  fake LLM) and an ingested demo corpus fixture.

Tests

- `uv run pytest`: 81 passed. Covers the five expected demo relations with provenance,
  team-name variant merge, idempotent re-ingest, duplicate upload, document removal,
  rate limit mid-ingestion (document failed, no partial data), unsupported evidence
  logged, PDF without a text layer.

## 2026-10-25 — Task 7: traversal and retrievers

Added

- `app/graph/traversal.py`: breadth-first enumeration of simple paths (1 to `MAX_HOPS`
  edges, both edge directions, no revisits). Seeds are always expanded; other nodes with
  degree above `MAX_NODE_DEGREE` end a path but are not expanded. Output capped at
  `MAX_PATHS`. Scoring: mean cosine similarity between the question and each edge's fact
  text, times `HOP_DECAY^(hops-1)`, plus 0.1 when the path ends on a second seed.
- `app/retrieval/standard.py`: vector-only baseline (no graph imports, enforced by a test).
- `app/retrieval/graph.py`: query entity extraction (LLM, JSON), seed resolution,
  traversal, path ranking, evidence from path edge provenance plus mentions of path end
  nodes, cut to `MAX_EVIDENCE_CHUNKS`. Returns an explicit `route_reason` when no seed,
  no relation or no path qualifies.
- `app/retrieval/fusion.py`: weighted reciprocal rank fusion with per-retriever ranks kept.
- `app/retrieval/hybrid.py`: fuses both; `route = "vector_only"` with the reason when the
  graph contributes nothing.
- `app/retrieval/types.py`: `PathStep`, `GraphPath.render()`
  (`A -[LEADS]-> B <-[USES]- C`), `RetrievedChunk`, `RetrievalResult`.

Tests

- `uv run pytest`: 98 passed. Includes GraphRAG retrieving all three demo documents for
  the Alice question through `Alice -[LEADS]-> Autonomous Systems -[DEVELOPED]-> Project
  Falcon -[USES]-> EdgeCore`.

## 2026-10-25 — Task 8: grounded answers and query service

Added

- `app/answer/generator.py`: prompt with numbered evidence blocks `[S#]` (filename, page,
  chunk id, text) and graph facts `[P#]` (rendered path and the evidence blocks that
  support it). JSON reply with `answer`, `explanation`, `citations`,
  `insufficient_evidence`, `conflicts`. Citations not present in the prompt are removed
  into `invalid_citations`; an answer with no valid citation that does not declare
  insufficient evidence is marked `grounded = false`. Empty retrieval skips the LLM and
  returns an insufficient-evidence answer.
- `app/query.py`: `QueryService.run(question, mode, overrides)` for `standard`, `graph`
  and `hybrid`, with retrieval, generation and total timings, token usage, cache hits and
  estimated cost. Per-query overrides are limited to retrieval parameters and validated.
  Graph modes raise `GraphUnavailable` when Neo4j is not connected; standard mode still
  works.

Tests

- `uv run pytest`: 113 passed. Includes the Alice question end to end in all three modes
  with the fake LLM.

## 2026-10-25 — Task 9: HTTP API

Added

- `app/main.py`: app factory with lifespan service construction, CORS, routers.
- `app/services.py`: `build_services(settings)` wires SQLite registry, persistent Chroma
  (`data/runtime/chroma`), embedder, Groq client with disk cache, lazy Neo4j store,
  resolver, ingestion and query services.
- `app/graph/lazy.py`: `LazyGraph` connects to Neo4j on first use and retries after a
  10 s cooldown, so the API starts and serves read endpoints while Neo4j is down.
- `app/api/errors.py`: one error shape `{"error": {"code", "message"}}`. Mapping:
  upload rejections 400, validation 422, not found 404, `graph_unavailable` 503,
  `llm_not_configured` 503, `llm_rate_limited` 429, `llm_unavailable` 503,
  `llm_bad_response` 502, anything else 500 `internal_error` (logged, not leaked).
- Routes: `GET /api/health`, `GET /api/stats`, `GET /api/activity`;
  `POST /api/documents/upload`, `GET /api/documents`, `GET|DELETE /api/documents/{id}`,
  `POST /api/documents/{id}/ingest`, `GET /api/documents/{id}/chunks`,
  `GET /api/documents/{id}/errors`; `GET /api/graph/stats`, `GET /api/graph/entities`,
  `GET /api/graph/search`, `GET /api/graph/entities/{id}`,
  `GET /api/graph/entities/{id}/neighbors`, `GET /api/graph/subgraph`; `POST /api/query`.
  Upload and re-ingest refuse with 503 up front when the LLM key or Neo4j is missing.
  Ingestion runs as a background task, serialized by a lock.
- `backend/Dockerfile`, `.dockerignore`, Compose `backend` service (depends on healthy
  Neo4j, runtime data volume, health check).

Tests

- `uv run pytest`: 124 passed (11 API tests with `TestClient`).
- Manual: `uvicorn app.main:app` started without Neo4j and without a key;
  `/api/health` reported `degraded` with `neo4j: down` and `llm_configured: false`,
  `/api/stats` and a standard-mode query on the empty index returned normally.

Not yet verified

- Neo4j store against a live database, the Docker image build, and a live Groq run
  (Docker Desktop was not running and no key is configured). Planned for Task 15.

## 2026-10-25 — Task 10: benchmark corpus and questions (frozen)

Added

- `data/benchmark/`: 11 fictional documents (the 3 demo documents, 6 linked documents,
  2 distractors) and `questions.json` with 22 questions across 7 categories.
- `docs/evaluation.md`: corpus, question categories and integrity rules.
- `tests/test_benchmark_data.py`: question set shape, required documents exist, every
  answer keyword appears in the required documents, benchmark includes the demo corpus.

Tests

- `uv run pytest`: 127 passed.

This commit freezes the benchmark. No live evaluation run has happened before it.

## 2026-10-25 — Task 11: metrics, runner and evaluation API

Added

- `app/evaluation/metrics.py`: SQuAD-style normalization; keyword correctness (every
  group needs one alternative present as whole words); insufficient-evidence questions
  are correct only when the system declares insufficient evidence, and any other question
  is incorrect when it does; token F1; context recall over required documents; citation
  precision and recall over cited documents (path citations count the documents of their
  supporting chunks).
- `app/evaluation/runner.py`: `EvaluationService` with `load_corpus` (idempotent upload
  and ingest of `data/benchmark/`), `start` (background thread, one run at a time),
  `run_now`, `progress`, `export` (JSON or CSV). Each record holds the question,
  reference, required documents, mode, retrieved chunks with scores and retriever ranks,
  graph paths, seeds, route, answer, citations, timings, token usage and metrics. Run
  config records models, retrieval settings, indexed and benchmark document ids and
  `corpus_mismatch`. An LLM failure (for example a daily rate limit) marks the run
  `failed` with the reason and keeps the partial summary.
- CLI: `uv run python -m app.evaluation.runner --load-corpus --modes standard graph hybrid`.
- `app/api/evaluation.py`: `POST /api/evaluation/load-corpus`, `POST /api/evaluation/run`
  (202; 409 when a run is in progress), `GET /api/evaluation/runs`,
  `GET /api/evaluation/runs/{id}`, `GET /api/evaluation/runs/{id}/results`,
  `GET /api/evaluation/results` (latest), `GET /api/evaluation/runs/{id}/export?format=csv|json`.

Tests

- `uv run pytest`: 141 passed.

## 2026-10-25 — Task 12: frontend shell, overview and documents

Added

- `frontend/`: Next.js 15 (App Router, TypeScript), Tailwind CSS 4, shadcn/ui components,
  Motion, Cytoscape.js, Recharts, lucide icons. pnpm build scripts allow-listed in
  `pnpm-workspace.yaml`.
- Theme: dye palette tokens in `app/globals.css` (weld for Standard RAG, indigo for
  GraphRAG, woad teal for Hybrid, madder for errors), light and dark via
  `prefers-color-scheme`, reduced motion respected. Hanken Grotesk for UI text,
  JetBrains Mono only for ids and graph paths.
- `lib/api.ts` (typed client for every backend route, uniform `ApiError`),
  `lib/types.ts` (backend response models), `lib/use-api.ts` (load and poll hook),
  `lib/modes.ts` (mode and entity-type colors, formatting).
- `components/app-shell.tsx`: navigation rail with live service status (API, Neo4j,
  LLM key).
- Overview page: index counts, demo walkthrough, models in use, configuration warnings,
  recent activity.
- Documents page: drag-and-drop upload, status with polling while extraction runs,
  chunk viewer, extraction error viewer, re-ingest, remove with confirmation describing
  exactly what is deleted.
- `README.md`: architecture, setup, configuration, operating modes, API, demo, benchmark,
  tests, limitations, troubleshooting.

Tests

- `pnpm lint`: no findings. `pnpm build`: succeeded.
- Backend `uv run pytest`: 141 passed.

Decisions

- The shadcn CLI added a third-party `cn` package; it was replaced with the standard local
  `clsx` + `tailwind-merge` helper and removed.

## 2026-10-25 — Task 13: graph explorer and question answering

Added

- `components/graph-canvas.tsx`: Cytoscape canvas with color and shape per entity type
  (shape duplicates the color encoding for readers who cannot rely on color), node size
  by degree, labeled directed edges, selection that fades unrelated elements, incremental
  updates with a cose layout.
- Graph page: entity search, node panel (type, description, aliases, relationships,
  mentions with file, page and chunk), relationship panel (type, confidence, every
  supporting sentence with its document and chunk), double-click to load a two-hop
  neighborhood, legend of types present.
- `components/path-thread.tsx`: graph paths rendered as entity chips joined by relation
  strands that draw in sequence when an answer arrives; direction shown by arrowheads.
- `components/answer-card.tsx`: generated answer visually separated from retrieved
  evidence and labeled with the model; flags for insufficient evidence, missing valid
  citations, removed citations and conflicts; citation chips that highlight the cited
  evidence block or path; collapsible evidence list with scores and per-retriever ranks;
  retrieval details (route and reason, seed entities and match method, timings, LLM calls,
  cache hits, tokens).
- Ask page: mode selector (Standard RAG, GraphRAG, Hybrid GraphRAG, Compare all), compare
  view in three columns, example questions from the benchmark. Compare runs the modes
  sequentially to stay inside free-tier rate limits.
- Removed unused create-next-app assets.

Tests

- `pnpm lint`: no findings. `pnpm build`: succeeded.

Not yet verified

- Rendering against a live backend with real data (requires Neo4j and an LLM key).
