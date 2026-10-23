# Loom Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task by
> task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the GraphRAG application described in `docs/design.md`: ingestion, graph
construction, three retrieval modes, grounded answers, benchmark, and web UI.

**Architecture:** Synchronous FastAPI backend (`backend/app`) over Neo4j, embedded
ChromaDB and SQLite, with an OpenAI-compatible LLM client pointed at Groq. Every store
and the LLM sit behind a `Protocol`; tests use in-memory or fake implementations.
Next.js frontend (`frontend/`) talks to the backend over HTTP.

**Tech Stack:** Python 3.11, uv, FastAPI, Pydantic v2, pydantic-settings, httpx,
neo4j driver, chromadb, pypdf, pytest; Next.js, TypeScript, Tailwind, shadcn/ui,
Cytoscape.js, Recharts, Motion; Docker Compose with Neo4j 5 Community.

**Spec:** `docs/design.md` (requirements: `docs/brief.md`)

Execution method: native (user instruction: implement without stopping for review).

## Global Constraints

- Python `>=3.11`; package manager uv; frontend package manager pnpm.
- No paid services. Default `LLM_BASE_URL=https://api.groq.com/openai/v1`,
  `EXTRACTION_MODEL=llama-3.3-70b-versatile`, `ANSWER_MODEL=llama-3.1-8b-instant`.
- Temperature 0 for every LLM call; every LLM call goes through the disk cache unless
  `LLM_CACHE=false`.
- No fake LLM output outside `backend/tests/`. Missing `LLM_API_KEY` returns HTTP 503
  with code `llm_not_configured`.
- All Cypher parameterized. Only integers validated in Python may be interpolated.
- Error body shape: `{"error": {"code": str, "message": str}}`.
- All modes share `MAX_EVIDENCE_CHUNKS` (default 6).
- Never log API keys. README and docs: professional, technical, no emojis.
- Each task ends with: tests green, `docs/progress.md` entry, commit, `git push origin main`.

## Review Focus

1. Neo4j not running at startup: the API starts, `/api/health` reports
   `neo4j: down`, graph and ingest endpoints return 503 `graph_unavailable`, not 500.
   Test in Task 9.
2. LLM rate limit or outage mid-ingestion: document ends `failed` with the reason, and
   its partial graph and vector contribution is removed. Test in Task 6.
3. PDF with no text layer, or an empty file: document ends `failed` with
   `no extractable text`. Test in Task 3.
4. Question naming no known entity: GraphRAG returns no evidence and the answer reports
   insufficient evidence; Hybrid reports `route = "vector_only"`. Test in Task 8.
5. Same file uploaded twice: same `document_id`, no duplicate chunks, nodes or edges.
   Test in Task 6.

---

### Task 1: Scaffold, config, LLM provider and cache

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/config.py`,
  `backend/app/logging.py`, `backend/app/llm/__init__.py`, `backend/app/llm/provider.py`,
  `backend/app/llm/cache.py`, `docker-compose.yml`, `.env.example`, `.gitignore`,
  `docs/progress.md`
- Test: `backend/tests/test_llm_provider.py`

**Interfaces:**
- Produces:
  - `Settings` (pydantic-settings, reads `.env` at repo root) and `get_settings() -> Settings`
    with every variable named in design sections 7, 8, 10.
  - `LLMError(Exception)` with `code: str`; subclasses `LLMNotConfigured`,
    `LLMRateLimited`, `LLMUnavailable`, `LLMBadResponse`.
  - `LLMUsage(model, prompt_tokens, completion_tokens, latency_ms, cached)` dataclass.
  - `LLMResponse(text: str, usage: LLMUsage)` dataclass.
  - `LLMProvider` Protocol: `complete(messages: list[dict], *, model: str,
    json_mode: bool = False, max_tokens: int = 1024) -> LLMResponse`.
  - `OpenAICompatibleLLM(base_url, api_key, timeout_s, max_rpm, max_retries,
    cache: LLMCache | None, transport: httpx.BaseTransport | None = None)`.
  - `LLMCache(path)`: `get(key) -> dict | None`, `set(key, value: dict)`,
    `make_key(model, messages, json_mode, max_tokens) -> str` (SHA-256 hex).

- [ ] Write tests using `httpx.MockTransport`:
  `test_complete_returns_text_and_usage`, `test_missing_key_raises_not_configured`
  (no HTTP request made), `test_429_retries_then_succeeds` (first response 429 with
  `retry-after: 0`, second 200; two requests), `test_429_exhausted_raises_rate_limited`,
  `test_cache_hit_skips_http_and_marks_cached`, `test_json_mode_sets_response_format`.
- [ ] Run `uv run pytest tests/test_llm_provider.py`; expect failures.
- [ ] Implement. Throttle is a sliding 60 s window under a lock. Backoff
  `min(retry_after or 2**attempt, 30)` seconds. 5xx and transport errors retry too; then
  `LLMUnavailable`.
- [ ] Tests pass. Compose file: `neo4j:5-community`, `NEO4J_AUTH` from env,
  `NEO4J_server_memory_heap_max__size=1G`, `NEO4J_server_memory_pagecache_size=512M`,
  volume `neo4j_data`, health check `cypher-shell ... 'RETURN 1'`. Backend and frontend
  services added in Task 9 and Task 14.
- [ ] Commit `feat: scaffold backend, config and LLM provider`, push.

### Task 2: Registry

**Files:** Create `backend/app/registry.py`; Test `backend/tests/test_registry.py`

**Interfaces:**
- Produces `Registry(db_path: Path)` with:
  `upsert_document(id, filename, content_type, size_bytes) -> DocumentRow` (existing id
  keeps its row, resets nothing), `get_document(id) -> DocumentRow | None`,
  `list_documents() -> list[DocumentRow]`, `set_status(id, status, error=None, **counts)`,
  `delete_document(id)`, `add_extraction_error(document_id, chunk_id, message, raw)`,
  `clear_extraction_errors(document_id)`, `list_extraction_errors(document_id)`,
  `log_activity(kind, message)`, `recent_activity(limit=20)`,
  `create_eval_run(config: dict) -> str`, `finish_eval_run(run_id, status, summary)`,
  `add_eval_result(run_id, question_id, mode, record: dict)`, `get_eval_run(run_id)`,
  `latest_eval_run()`, `list_eval_runs()`, `eval_results(run_id) -> list[dict]`.
  `DocumentRow` is a Pydantic model mirroring the `documents` table.
- [ ] Tests: round-trip each method on a `tmp_path` database; `upsert_document` twice
  keeps one row.
- [ ] Implement with `sqlite3`, one connection per call, `PRAGMA journal_mode=WAL`.
- [ ] Commit, push.

### Task 3: Parsing and chunking

**Files:** Create `backend/app/ingestion/__init__.py`, `parsing.py`, `chunking.py`,
`backend/app/models.py`; Test `backend/tests/test_parsing.py`, `test_chunking.py`

**Interfaces:**
- Produces in `app/models.py`: `ChunkRecord(id, document_id, filename, page: int | None,
  chunk_index, text, char_start, char_end)` (Pydantic).
- Produces in `parsing.py`: `Page(number: int | None, text: str)`;
  `UploadRejected(Exception)` with `code`; `validate_upload(filename: str, data: bytes,
  max_bytes: int) -> str` returns the extension; `document_id_for(data: bytes) -> str`
  (16 hex chars of SHA-256); `parse_file(path: Path) -> list[Page]`;
  `NoExtractableText(Exception)`.
- Produces in `chunking.py`: `chunk_pages(pages, document_id, filename, size, overlap)
  -> list[ChunkRecord]`.
- [ ] Tests: `.exe` rejected (`unsupported_type`); oversize rejected (`too_large`);
  `.pdf` without `%PDF` magic rejected; PDF fixture generated in-test with pypdf's
  writer plus a text page (use `reportlab` only if pypdf cannot write text; otherwise a
  minimal hand-written PDF bytes fixture) yields page numbers; empty `.txt` raises
  `NoExtractableText`; chunker: 2500-char text, size 1000, overlap 150 gives 3 chunks,
  consecutive chunks overlap, ids `{doc}:{i}`, chunks never span pages, short text gives
  1 chunk.
- [ ] Implement. Break point: last `\n\n`, else last `. `, inside the final 30% of the
  window; else hard cut.
- [ ] Commit, push.

### Task 4: Vector store

**Files:** Create `backend/app/vector/__init__.py`, `backend/app/vector/store.py`;
Test `backend/tests/test_vector_store.py`, `backend/tests/fakes.py`

**Interfaces:**
- Produces: `ScoredChunk(chunk: ChunkRecord, score: float)`; `VectorStore` Protocol and
  `ChromaVectorStore(client, embedding_function, collection_prefix: str)` with
  `upsert_chunks(chunks)`, `delete_document(document_id)`,
  `search(query: str, k: int, min_score: float) -> list[ScoredChunk]` (score = cosine
  similarity, descending), `get_chunks(ids) -> list[ChunkRecord]` (input order kept,
  missing skipped), `chunks_for_document(document_id) -> list[ChunkRecord]` sorted by
  index, `count_chunks() -> int`, `upsert_entities(items: list[tuple[str, str, str]])`
  (id, text, type), `delete_entities(ids)`,
  `search_entities(query, k) -> list[tuple[str, float]]`,
  `embed(texts) -> list[list[float]]`.
  `make_embedding_function(model_name)`: `all-MiniLM-L6-v2` gives Chroma's ONNX
  default; anything else gives `SentenceTransformerEmbeddingFunction` (optional
  dependency, clear error if missing). Collection names include a slug of the model
  name so a model change never mixes dimensions.
- Produces in `tests/fakes.py`: `HashEmbedding` (deterministic bag-of-words hashing into
  256 dims, L2-normalized, Chroma `EmbeddingFunction`), `FakeLLM(responses:
  list[tuple[str, str]])` returning the response whose key substring occurs in the last
  user message, raising if none matches, recording calls.
- [ ] Tests on `chromadb.EphemeralClient()` with `HashEmbedding`: upsert twice gives
  same count; search ranks the chunk sharing words first; `min_score` filters;
  delete_document removes only that document; entity search returns the matching id.
- [ ] Implement with cosine space.
- [ ] Commit, push.

### Task 5: Extraction, normalization, graph stores

**Files:** Create `backend/app/extraction/{__init__,schema,normalize,extractor}.py`,
`backend/app/graph/{__init__,store,memory_store,neo4j_store}.py`;
Test `backend/tests/test_extraction.py`, `test_normalize.py`, `test_graph_store.py`

**Interfaces:**
- Produces in `schema.py`: `ENTITY_TYPES` tuple (design 7.2);
  `ExtractedEntity(name, type, aliases: list[str] = [], description: str = "")`,
  `ExtractedRelation(source, target, type, evidence, confidence: float = 0.7)`,
  `ExtractionResult(entities, relations)`; validators coerce type to enum/OTHER, relation
  type to `UPPER_SNAKE_CASE`, clamp confidence.
- Produces in `normalize.py`: `normalize_name(s) -> str`, `entity_id(name) -> str`
  (normalized key with spaces as `-`), `evidence_supported(evidence, text) -> bool`.
- Produces in `extractor.py`: `ExtractionParseError`;
  `validate_extraction(raw: str, chunk_text: str) -> tuple[ExtractionResult, list[str]]`
  (warnings list names each dropped relation and why);
  `extract_chunk(llm, model, chunk_text) -> tuple[ExtractionResult, list[str],
  list[LLMUsage]]` (one retry on `ExtractionParseError` with the error appended).
- Produces in `graph/store.py`: `Entity(id, name, type, aliases, description,
  degree=0)`, `Relation(source, target, type, chunk_ids, document_ids, evidence,
  confidence)`, `Mention(chunk_id, document_id, filename, page)`, `GraphUnavailable`,
  and `GraphStore` Protocol:
  `upsert_entity(entity: Entity, mention: Mention)`,
  `upsert_relation(source_id, target_id, type, mention: Mention, evidence, confidence)`,
  `get_entity(id)`, `get_entities(ids) -> list[Entity]`,
  `find_entities(q: str | None, type: str | None, limit: int) -> list[Entity]`,
  `entity_index() -> list[tuple[str, list[str]]]` (id, aliases),
  `neighbors(ids: list[str]) -> list[Relation]` (both directions),
  `mentions(ids: list[str]) -> dict[str, list[Mention]]`,
  `remove_document(document_id) -> list[str]` (ids of deleted entities),
  `recompute_degrees()`, `stats() -> dict`, `subgraph(limit) -> tuple[list[Entity],
  list[Relation]]`, `clear()`.
  Entity type: the first non-OTHER type assigned wins (simplification of design 7.3,
  recorded in progress).
- Produces: `InMemoryGraphStore()` and `Neo4jGraphStore(uri, user, password)`, the
  latter creating the unique constraint on startup and raising `GraphUnavailable` on
  connection errors.
- [ ] Tests (extraction): malformed JSON raises; missing `relations` key yields empty
  list; unknown type becomes OTHER; `leads` becomes `LEADS`; relation with unknown
  endpoint dropped with warning; relation whose evidence is not in the chunk dropped;
  evidence with different case and whitespace kept; retry path calls the LLM twice.
- [ ] Tests (normalize): `"The Acme  Technologies."` and `"acme technologies"` share a
  key; `entity_id("Project Falcon") == "project-falcon"`.
- [ ] Tests (graph store), parametrized over `InMemoryGraphStore` and, when
  `NEO4J_TEST_URI` is set, `Neo4jGraphStore`: upserting the same relation twice from the
  same chunk gives one edge with one chunk id; from a second document appends provenance;
  `remove_document` drops edges with no provenance and entities with no mentions;
  `neighbors` returns incoming and outgoing edges.
- [ ] Implement. Neo4j `remove_document` uses list comprehensions to filter provenance
  lists, then deletes empty edges and orphan entities in the same transaction.
- [ ] Commit, push.

### Task 6: Entity resolution and ingestion pipeline

**Files:** Create `backend/app/graph/resolution.py`, `backend/app/ingestion/pipeline.py`,
`backend/tests/fixtures/demo_llm.py`, `data/demo/{employee,project,technology}.md`;
Test `backend/tests/test_resolution.py`, `test_pipeline.py`

**Interfaces:**
- Produces: `EntityResolver(graph: GraphStore, vector: VectorStore, fuzzy_threshold=0.92)`
  with `refresh()`, `resolve_ingest(name: str, aliases: list[str]) -> str | None`
  (existing id or None), `resolve_query(mentions: list[str], question: str,
  min_score: float, limit: int) -> list[SeedMatch]` where
  `SeedMatch(entity_id, mention, score, method: Literal["exact","alias","fuzzy",
  "embedding","scan"])`. Query fuzzy threshold 0.85.
- Produces: `IngestionService(settings, registry, vector, graph, llm)` with
  `ingest(document_id) -> None` (never raises; records status) and
  `remove(document_id) -> None`.
- Produces in `fixtures/demo_llm.py`: `demo_fake_llm() -> FakeLLM` with canned
  extraction JSON for the three demo documents and canned answers for the Alice question.
- [ ] Tests (resolution): alias match returns the existing id; `"Acme Tech"` vs
  `"Acme Technologies"` does not merge at 0.92; scan finds `"Alice"` in the question
  text; embedding match uses `search_entities`.
- [ ] Tests (pipeline, demo corpus, FakeLLM, InMemoryGraphStore, ephemeral Chroma): all
  five design relations exist with the right `document_ids`; status `ingested` with
  counts; ingesting the same document again leaves node, edge and chunk counts unchanged;
  FakeLLM raising `LLMRateLimited` on the second chunk leaves the document `failed` with
  the message and no chunks or mentions from it; `remove` deletes everything from that
  document only.
- [ ] Implement: remove prior contribution, parse, chunk, upsert chunks, extract per
  chunk, resolve and upsert entities and relations, upsert entity texts into the vector
  `entities` collection, recompute degrees, set counts, log activity. On any exception:
  remove contribution, set `failed`.
- [ ] Commit, push.

### Task 7: Traversal and the three retrievers

**Files:** Create `backend/app/graph/traversal.py`,
`backend/app/retrieval/{__init__,types,standard,graph,fusion,hybrid}.py`;
Test `backend/tests/test_traversal.py`, `test_retrieval.py`

**Interfaces:**
- Produces in `retrieval/types.py`: `PathStep(source_id, source_name, type, target_id,
  target_name, forward: bool)`, `GraphPath(steps: list[PathStep], score: float,
  chunk_ids: list[str])` with `render() -> str` giving `A -[LEADS]-> B <-[USES]- C`,
  `RetrievedChunk(chunk: ChunkRecord, score: float, sources: dict[str, dict])`,
  `RetrievalResult(mode, chunks, paths, seeds: list[SeedMatch], route: str,
  route_reason: str, latency_ms: float, usage: list[LLMUsage])`.
- Produces in `traversal.py`: `enumerate_paths(graph, seed_ids, max_hops, max_degree,
  max_paths) -> list[list[tuple[Relation, bool]]]` (edge plus forward flag);
  `score_paths(paths, query_vec, edge_vecs: dict[str, list[float]], hop_decay,
  seed_ids, min_score, top_k) -> list[tuple[list, float]]`; edge key
  `f"{source}|{type}|{target}"`. Seed-to-seed bonus +0.1.
- Produces: `retrieve_standard(vector, question, settings) -> RetrievalResult`;
  `retrieve_graph(question, *, llm, vector, graph, resolver, settings) ->
  RetrievalResult`; `rrf_fuse(rankings: dict[str, list[RetrievedChunk]], weights:
  dict[str, float], k: int, limit: int) -> list[RetrievedChunk]`;
  `retrieve_hybrid(question, **same deps) -> RetrievalResult`.
- [ ] Tests (traversal on a hand-built InMemoryGraphStore): chain of 5 edges with
  `max_hops=3` yields no path longer than 3; hub node with degree above the limit is an
  endpoint but not expanded; cycle A-B-C-A not revisited; `max_paths` caps output;
  path whose edge vectors match the query outranks one that does not; longer path
  decayed.
- [ ] Tests (retrieval): `rrf_fuse` deduplicates a chunk present in both lists and
  merges `sources`; budget cut at `limit`; standard retrieval imports nothing from
  `app.graph`; graph retrieval on the demo corpus (from Task 6 fixtures) returns chunks
  from all three demo documents for the Alice question; question about an unknown
  entity gives empty graph result and hybrid `route == "vector_only"`.
- [ ] Implement. Query-entity call prompt asks for a JSON list of entity strings,
  `QUERY_ENTITY_MODEL`.
- [ ] Commit, push.

### Task 8: Answer generation and query service

**Files:** Create `backend/app/answer/{__init__,generator}.py`, `backend/app/query.py`;
Test `backend/tests/test_answer.py`, `test_query_integration.py`

**Interfaces:**
- Produces: `Citation(id: str, kind: Literal["chunk","path"], chunk_id, document_id,
  filename, page, path: str | None)`; `Answer(answer, explanation, citations:
  list[Citation], insufficient_evidence: bool, conflicts: list[str],
  invalid_citations: list[str], grounded: bool, usage: LLMUsage | None)`;
  `build_messages(question, chunks, paths) -> list[dict]`;
  `parse_answer(raw: str, chunks, paths) -> Answer`;
  `generate_answer(llm, model, question, retrieval) -> Answer`. Empty retrieval skips the
  LLM and returns `insufficient_evidence=True`.
- Produces in `query.py`: `QueryService(deps)` with `run(question, mode, overrides:
  dict | None) -> QueryResponse` (Pydantic: question, mode, answer, retrieval,
  timings `{retrieval_ms, generation_ms, total_ms}`, usage totals).
- [ ] Tests: `S9` removed into `invalid_citations`; zero valid citations and
  `insufficient_evidence=false` gives `grounded=false`; path citation resolves to the
  rendered path; malformed answer JSON raises `LLMBadResponse`; empty retrieval makes no
  LLM call.
- [ ] Integration: demo corpus ingested with FakeLLM, `QueryService.run` in each mode for
  the Alice question returns an answer whose citations resolve to demo filenames.
- [ ] Commit, push.

### Task 9: API

**Files:** Create `backend/app/services.py`, `backend/app/main.py`,
`backend/app/api/{__init__,errors,documents,graph,query,evaluation,system}.py`,
`backend/Dockerfile`; Modify `docker-compose.yml`; Test `backend/tests/test_api.py`

**Interfaces:**
- Produces: `Services` container (settings, registry, vector, graph | None, llm,
  resolver, ingestion, query, evaluation) built by `build_services(settings)`; app factory
  `create_app(services: Services | None = None) -> FastAPI`. Graph connection is
  attempted lazily; failure gives `GraphUnavailable` mapped to 503 `graph_unavailable`.
- Routes: design section 12. Upload stores file under `data/uploads/`, upserts registry
  row, schedules `ingestion.ingest` as a `BackgroundTasks` job, returns rows.
- [ ] Tests with `TestClient` and fakes: upload `.md` then poll document to `ingested`;
  upload `.exe` returns 400 `unsupported_type`; `DELETE` returns 204 and the document is
  gone; `POST /api/query` with invalid mode returns 422; services with `graph=None`
  return 503 on `/api/graph/stats` and `/api/health` reports `neo4j: down`; LLM without
  key returns 503 `llm_not_configured` on query.
- [ ] Manual: `docker compose up -d neo4j`, `uv run uvicorn app.main:app`, upload demo
  docs with Groq key, ask the Alice question in all modes; record outcome in progress.
- [ ] Commit, push.

### Task 10: Benchmark corpus and questions (frozen before any live run)

**Files:** Create `data/benchmark/*.md` (demo docs plus about 9 more),
`data/benchmark/questions.json`, `docs/evaluation.md`

- [ ] Write documents and at least 20 questions covering the seven categories of design
  11.1, at least 3 per multi-hop category and at least 2 `insufficient_evidence`.
  Each question: `id, question, category, reference_answer, answer_keywords:
  list[list[str]], required_documents: list[str]` (filenames).
- [ ] Validation test `backend/tests/test_benchmark_data.py`: every
  `required_documents` filename exists; every keyword alternative occurs in at least one
  required document (case-insensitive) except for `insufficient_evidence` questions,
  which have empty keywords and empty required documents; ids unique; count >= 20.
- [ ] Commit `data: freeze benchmark corpus and questions`, push.

### Task 11: Metrics and runner

**Files:** Create `backend/app/evaluation/{__init__,dataset,metrics,runner}.py`;
Test `backend/tests/test_metrics.py`, `test_runner.py`

**Interfaces:**
- Produces: `Question` model; `load_questions(path) -> list[Question]`;
  metrics `normalize_answer(s)`, `keyword_correct(answer, keyword_groups) -> bool`,
  `token_f1(pred, ref) -> float`, `context_recall(retrieved_filenames, required) ->
  float | None`, `citation_scores(cited_filenames, required) -> tuple[float | None,
  float | None]`; `EvaluationService(services)` with `load_corpus() -> list[str]`,
  `start(modes: list[str]) -> str` (run id, background thread, one run at a time),
  `progress(run_id) -> dict`, `export(run_id, fmt) -> tuple[str, str]` (content, media
  type). Per-record fields: design 11 and brief section 4.
- [ ] Tests: keyword groups all-of/any-of; F1 on known pairs (`"the cat sat"` vs
  `"cat sat down"` = 0.8); recall None when no required docs; insufficient question
  correct only when flagged; runner on demo corpus with FakeLLM writes one result per
  question per mode and a summary with per-mode means; `corpus_mismatch` true when an
  extra document is indexed; CSV export has a header row and one row per result.
- [ ] Add CLI `python -m app.evaluation.runner --modes standard graph hybrid`.
- [ ] Commit, push.

### Task 12: Frontend shell, API client, dashboard, documents

**Files:** Create `frontend/` (Next.js app router, Tailwind, shadcn/ui init), `frontend/
lib/api.ts` (typed fetch wrappers for every backend route, base URL from
`NEXT_PUBLIC_API_URL`), `frontend/lib/types.ts` (mirrors backend response models),
`frontend/components/app-shell.tsx`, `frontend/app/page.tsx` (dashboard),
`frontend/app/documents/page.tsx`

- [ ] Dashboard: stat cards with Motion count-up, activity feed, health.
- [ ] Documents: drag-drop upload, status polling every 2 s while any document is
  `processing`, chunk drawer, errors drawer, re-ingest, delete with confirm dialog.
- [ ] `pnpm build` and `pnpm lint` pass; manual check against running backend.
- [ ] Commit, push.

### Task 13: Graph explorer and Ask page

**Files:** Create `frontend/app/graph/page.tsx`, `frontend/components/graph-canvas.tsx`,
`frontend/app/ask/page.tsx`, `frontend/components/answer-card.tsx`,
`frontend/components/evidence-list.tsx`

- [ ] Graph: Cytoscape with `cose` layout, color and shape per entity type, legend,
  search, node panel (aliases, description, mentions), edge panel (type, evidence,
  documents, confidence), double-click expands neighbors.
- [ ] Ask: thread, mode selector, compare-all-modes view in three columns, answer card
  separated from evidence, citation chips scroll to evidence, rendered paths, collapsible
  retrieval details (scores, retriever ranks, route, timings, tokens).
- [ ] Build and lint pass; manual check.
- [ ] Commit, push.

### Task 14: Evaluation dashboard and Compose services

**Files:** Create `frontend/app/evaluation/page.tsx`, `frontend/components/eval-charts.tsx`,
`frontend/Dockerfile`; Modify `docker-compose.yml`

- [ ] Run button with mode checkboxes and progress, load-corpus button, summary table,
  Recharts bar charts per metric and per category, per-question table with filter for
  failures, drill-down drawer with each mode's chunks, paths and answer, CSV and JSON
  export, corpus mismatch and cache-hit notices.
- [ ] Compose `backend` and `frontend` services; `docker compose up` starts all three.
- [ ] Commit, push.

### Task 15: Live benchmark and documentation

**Files:** Create `README.md`, `docs/architecture.md`, `docs/api.md`,
`docs/configuration.md`; Modify `docs/evaluation.md`, `docs/progress.md`

- [ ] With Groq key: load corpus, run benchmark in all modes, export JSON to
  `docs/results/` and copy the summary table, unchanged, into `docs/evaluation.md`
  with date, models and config.
- [ ] README: overview, architecture, prerequisites, setup (Compose and local), config,
  operating modes, API summary, demo walkthrough, benchmark, tests, limitations,
  troubleshooting.
- [ ] Full test suite run; result recorded in progress.
- [ ] Commit, push.
