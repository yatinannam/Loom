# Loom: GraphRAG for Multi-Hop Question Answering — Design

Status: draft for approval
Date: 2026-10-23

## 1. Intent

Loom answers multi-hop questions over an uploaded document corpus by combining
knowledge-graph traversal with vector retrieval, and measures, on the same corpus
and the same LLM, whether that beats a standard vector-only RAG baseline.

The project exists to demonstrate one claim with real evidence: when an answer is
distributed across several documents and connected only through shared entities,
graph traversal recovers evidence that similarity search misses. Every number the
application reports must come from an actual run.

The full requirement list is the original task brief, kept verbatim in
[`brief.md`](brief.md); this document records how it will be built and the decisions
taken. Section numbers prefixed "brief" refer to that file.

Smoke-test scenario (brief section 1). Three documents:

- A: "Alice works at Acme Technologies and leads the Autonomous Systems team."
- B: "The Autonomous Systems team developed Project Falcon, which uses the EdgeCore
  platform."
- C: "EdgeCore is maintained by a separate infrastructure team and is deployed on
  NVIDIA Jetson devices."

Question: "Which hardware platform is used by the project led by Alice's team, and
which technology connects the project to that hardware?" Expected: NVIDIA Jetson,
connected through EdgeCore. Expected relations: Alice WORKS_AT Acme Technologies,
Alice LEADS Autonomous Systems, Autonomous Systems DEVELOPED Project Falcon,
Project Falcon USES EdgeCore, EdgeCore DEPLOYED_ON NVIDIA Jetson.

Note that NVIDIA Jetson is four hops from Alice. With the default `MAX_HOPS = 3` the
traversal reaches EdgeCore, and document C enters the evidence through EdgeCore's
mentions (section 8.2 step 5). This is intended behavior, not a special case.

## 2. Goals, non-goals, anti-goals

Goals

- Working end-to-end pipeline: upload, parse, chunk, embed, extract, build graph,
  query in three modes, grounded answer with citations.
- Three switchable retrieval modes: Standard RAG, GraphRAG, Hybrid GraphRAG.
- Reproducible benchmark (at least 20 questions) with deterministic metrics,
  comparison table, charts, per-query inspection, CSV/JSON export.
- Web UI: dashboard, documents, graph explorer, question answering, evaluation.
- Runs entirely on free resources: Groq free tier for the LLM, local CPU embeddings,
  Neo4j Community and ChromaDB locally.

Non-goals

- Multi-user accounts, authentication, multi-tenancy.
- Horizontal scale or corpora beyond a few hundred documents.
- OCR for scanned PDFs (text-layer PDFs only).
- Fine-tuning or training any model.

Anti-goals (failure even if it technically works)

- Hard-coded or tuned-to-win benchmark results, or any answer path that special-cases
  the demo corpus.
- Silent fallback to fake model output when the LLM is unavailable. Missing key or
  provider outage returns a clear error.
- Relationships in the graph that the source text does not support.
- An answer presented as verified when it was not checked against evidence.
- Exhausting the Groq free quota through repeated identical calls.

## 3. Constraints

- Hardware: Samsung Galaxy Book 5, 16 GB RAM, no discrete GPU. Local LLM inference is
  not the default; embeddings run on CPU.
- Cost: everything free. Groq free tier has per-minute and per-day request and token
  limits that differ per model and change over time.
- Installed toolchain: Python 3.11 (not 3.12), Node 24, pnpm, uv, Docker.
- Git: push to `main` on `https://github.com/yatinannam/Loom.git` after each milestone.
- Documentation lives in `docs/` and is updated with every milestone. README is
  professional and technical, no emojis.

## 4. Stack

| Concern | Choice | Reason |
|---|---|---|
| API | Python 3.11, FastAPI, Pydantic v2, pydantic-settings | Brief default; 3.11 is installed |
| Python packaging | uv with `pyproject.toml` | Installed, fast, lockfile |
| Graph store | Neo4j 5 Community (Docker) | Brief default, free |
| Vector store | ChromaDB embedded `PersistentClient` | No extra server process |
| Embeddings | Chroma's built-in ONNX `all-MiniLM-L6-v2` | Free, CPU, no PyTorch download; model name configurable |
| LLM | Groq via OpenAI-compatible HTTP API (httpx) | Free tier; same client works with Ollama or any OpenAI-compatible endpoint by changing `LLM_BASE_URL` |
| PDF parsing | pypdf | Pure Python, page numbers |
| App metadata | SQLite (stdlib `sqlite3`) | Document registry, ingestion status and errors, activity log, evaluation runs |
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn/ui | Brief default |
| Graph visualization | Cytoscape.js (react-cytoscapejs) | Mature, handles typed styling and click events |
| Charts | Recharts | Brief default |
| Animation | Motion (formerly Framer Motion) | Page transitions, staggered lists, count-up stats |
| Tests | pytest with deterministic fake LLM and fake embedder | No live calls in tests |

Decision: GSAP and Lenis are not used. The app is a dashboard with internally
scrolling panels; Lenis smooth scroll interferes with nested scroll containers, and
Motion covers the transitions needed with React-native APIs.

## 5. Architecture

```
frontend (Next.js)  --HTTP-->  backend (FastAPI)
                                 |-- ingestion  -> parsing, chunking
                                 |-- extraction -> LLM JSON extraction + validation
                                 |-- graph      -> Neo4j store, entity resolution, traversal
                                 |-- vector     -> Chroma store (chunks, entity names)
                                 |-- llm        -> provider, rate limiter, disk cache
                                 |-- retrieval  -> standard, graph, hybrid (fusion)
                                 |-- answer     -> prompt, JSON answer, citation check
                                 |-- evaluation -> dataset, runner, metrics
                                 |-- registry   -> SQLite documents/activity/eval runs
```

Interfaces (Python `Protocol`): `LLMProvider`, `Embedder`, `VectorStore`,
`GraphStore`. Production implementations: `OpenAICompatibleLLM`, `ChromaVectorStore`
(embedding via Chroma's function), `Neo4jGraphStore`. Test implementations:
`FakeLLM` (canned responses keyed by prompt content), `InMemoryGraphStore`, and an
ephemeral Chroma client with a deterministic hashing embedder.

Graph traversal is implemented in Python over `GraphStore.neighbors(entity_ids)`
rather than as one variable-length Cypher query, so hop limits, degree guards and path
scoring are explicit and unit-testable against the in-memory store.

### Repository layout

```
backend/
  pyproject.toml
  app/
    main.py config.py logging.py
    api/          documents.py graph.py query.py evaluation.py stats.py
    ingestion/    parsing.py chunking.py pipeline.py
    extraction/   schema.py extractor.py normalize.py
    graph/        store.py neo4j_store.py memory_store.py resolution.py traversal.py
    vector/       store.py
    llm/          provider.py cache.py ratelimit.py
    retrieval/    standard.py graph.py hybrid.py fusion.py
    answer/       generator.py
    evaluation/   dataset.py metrics.py runner.py
    registry.py
  tests/
data/
  demo/         three-document smoke corpus (Alice / Acme / Falcon / EdgeCore)
  benchmark/    larger fictional corpus + questions.json
frontend/
docs/
docker-compose.yml
.env.example
README.md
```

## 6. Data model

Identifiers

- `document_id` = first 16 hex chars of SHA-256 of file bytes. Re-uploading the same
  file maps to the same document.
- `chunk_id` = `{document_id}:{chunk_index}`.
- `entity_id` = normalized canonical name (see 7.3), slug form.

Chroma collections

- `chunks`: id `chunk_id`, document text, metadata `document_id`, `filename`, `page`,
  `chunk_index`, `char_start`, `char_end`. Written with `upsert`.
- `entities`: id `entity_id`, document = `"{name}: {description}"`, metadata `type`.
  Used for embedding-based entity resolution of query mentions.

Neo4j

- `(:Entity {id, name, type, aliases: [..], description, degree})`, unique constraint
  on `id`.
- `(:Chunk {id, document_id, filename, page})`.
- `(:Entity)-[:MENTIONED_IN]->(:Chunk)`.
- `(:Entity)-[:RELATES {type, chunk_ids: [..], document_ids: [..], evidence: [..],
  confidence}]->(:Entity)`. A single relationship label with a `type` property keeps
  every Cypher statement parameterized (relationship labels cannot be parameters).
  One `RELATES` edge per `(source, type, target)`; repeated mentions append provenance.

SQLite (`data/loom.db`)

- `documents(id, filename, content_type, size_bytes, status, error, pages,
  chunk_count, entity_count, relation_count, created_at, updated_at)`
  with status in `uploaded | processing | ingested | failed`.
- `extraction_errors(document_id, chunk_id, message, raw_response, created_at)`.
- `activity(id, kind, message, created_at)` for the dashboard feed.
- `eval_runs(id, created_at, config_json, summary_json)` and
  `eval_results(run_id, question_id, mode, record_json)`.

Uploaded files are stored at `data/uploads/{document_id}{ext}`.

## 7. Ingestion pipeline

### 7.1 Parse and chunk

- Accepted: `.pdf`, `.txt`, `.md`. Validated by extension and, for PDF, magic bytes.
  Size limit `MAX_UPLOAD_MB` (default 10).
- PDF: per-page text via pypdf; chunks never span pages, so every chunk has a page.
  TXT/MD: page is null.
- Chunker: character-based with overlap (`CHUNK_SIZE` default 1000,
  `CHUNK_OVERLAP` default 150), breaking at the nearest paragraph or sentence boundary
  inside the window.

### 7.2 Extraction

One LLM call per chunk in JSON mode with an explicit schema and entity-type enum:
`PERSON, ORGANIZATION, TEAM, PROJECT, PRODUCT, TECHNOLOGY, LOCATION, EVENT, CONCEPT,
OTHER`. Output schema:

```json
{
  "entities": [{"name": "...", "type": "PERSON", "aliases": [], "description": "..."}],
  "relations": [{"source": "...", "target": "...", "type": "LEADS",
                 "evidence": "exact supporting sentence", "confidence": 0.0}]
}
```

Validation (Pydantic, then semantic checks):

- Unparseable JSON: one retry with the parse error appended; then the chunk is recorded
  in `extraction_errors` and skipped. Ingestion of the rest continues.
- Unknown entity type maps to `OTHER`. Relation type is coerced to `UPPER_SNAKE_CASE`.
- Relations whose source or target is not among the extracted entities are dropped.
- Anti-hallucination check: a relation is kept only if its `evidence` appears in the
  chunk text after whitespace and case normalization, or has token overlap of at
  least 0.8 with some sentence in the chunk. Dropped relations are logged as errors.
- Confidence is clamped to [0, 1].

### 7.3 Normalization and entity resolution

- Normalized key: lowercase, Unicode NFKC, strip punctuation, collapse whitespace,
  strip a leading "the".
- Entity identity is the normalized name, independent of type (the same name typed
  TEAM in one chunk and ORGANIZATION in another is one node; the type is the most
  frequently assigned one).
- A new entity merges into an existing one when its normalized name equals an
  existing node's key or one of its aliases, or when difflib similarity >= 0.92 to an
  existing key. Aliases are unioned. Merges are conservative by design: a missed
  merge costs a hop, a wrong merge invents a connection.

### 7.4 Idempotency and removal

- Re-ingesting a document first removes its prior contribution (chunks from Chroma,
  its chunk ids from edge provenance lists, edges left with empty provenance, entities
  with no remaining mentions), then ingests again. Result: no duplicate chunks, nodes
  or edges.
- `DELETE /api/documents/{id}` performs the same removal plus file and registry
  deletion.
- Node `degree` is recomputed for affected nodes after each ingest or delete.

## 8. Retrieval

All three modes share one evidence budget: at most `MAX_EVIDENCE_CHUNKS` (default 6)
chunks reach the answer prompt. This keeps the comparison fair.

### 8.1 Standard RAG (baseline)

Embed query, Chroma similarity search over `chunks`, keep results with similarity >=
`VECTOR_MIN_SCORE` (default 0.2), top `MAX_EVIDENCE_CHUNKS`. No graph access.
Implemented in its own module with no dependency on graph code.

### 8.2 GraphRAG

1. Query entity mentions: one LLM call returning candidate entity strings from the
   question, plus a deterministic scan for known entity names and aliases appearing in
   the question text.
2. Resolve mentions to nodes: exact normalized key or alias, then difflib >= 0.85,
   then nearest neighbor in the `entities` collection with similarity >=
   `ENTITY_MIN_SCORE`. At most `MAX_SEED_ENTITIES` (default 5) seeds.
3. Bounded traversal: breadth-first from the seeds up to `MAX_HOPS` (default 3, hard
   cap 4). Nodes with degree above `MAX_NODE_DEGREE` (default 50) are kept as path
   endpoints but not expanded. At most `MAX_PATHS` (default 200) paths are
   enumerated; cycles are not followed.
4. Path scoring: mean cosine similarity between the query embedding and each edge's
   rendered fact text (`"source TYPE target: evidence"`), multiplied by
   `HOP_DECAY ** (hops - 1)` (default 0.85), plus a bonus when a path connects two
   distinct seeds. Paths below `PATH_MIN_SCORE` are discarded. Top `TOP_PATHS`
   (default 8) are kept.
5. Evidence collection: chunks referenced in the provenance of the kept paths' edges,
   plus chunks where the kept paths' terminal entities are mentioned, ranked by the
   best score of any path that contributed them.
6. Graph paths are passed to the answer prompt as readable fact lines in addition to
   chunk text.

### 8.3 Hybrid GraphRAG

Run 8.1 and 8.2, fuse chunk rankings with weighted Reciprocal Rank Fusion
(`score = sum(w_mode / (RRF_K + rank))`, `RRF_K` default 60, `VECTOR_WEIGHT` and
`GRAPH_WEIGHT` default 1.0), deduplicate by `chunk_id`, cut to the evidence budget.
Each chunk records which retriever(s) produced it and at which rank.

Routing: if no seed entity resolves or no path survives scoring, hybrid uses vector
results alone and reports `route = "vector_only"` with the reason. GraphRAG mode in the
same situation returns its empty result and the answer reports insufficient evidence;
it does not silently switch to vector search.

## 9. Answer generation

- Prompt contains numbered evidence blocks `[S1]..[Sn]` (filename, page, chunk text)
  and graph fact lines `[P1]..[Pm]`. The model is instructed to use only this evidence.
- JSON mode response:
  `{answer, explanation, citations: ["S1", "P2"], insufficient_evidence: bool,
  conflicts: [string]}`. `explanation` is a short evidence-based summary, not
  chain-of-thought.
- Post-validation: citation ids not present in the prompt are removed and reported as
  `invalid_citations`. An answer with zero valid citations and
  `insufficient_evidence = false` is flagged `ungrounded` in the response.
- Citations are resolved to `{filename, page, chunk_id}` for display; path citations
  resolve to the path plus its edges' provenance.
- The API never labels an answer verified. It reports `grounded` only in the narrow
  sense above.

## 10. LLM provider and the free tier

- `OpenAICompatibleLLM` posts to `{LLM_BASE_URL}/chat/completions` with httpx,
  default base `https://api.groq.com/openai/v1`, key from `LLM_API_KEY`.
- Separate models per role: `EXTRACTION_MODEL` (default `llama-3.3-70b-versatile`) and
  `ANSWER_MODEL` (default `llama-3.1-8b-instant`), plus `QUERY_ENTITY_MODEL` (default
  same as answer model). Defaults chosen because the 70B model has a much smaller free
  daily token budget than the 8B model.
- Client-side throttle `LLM_MAX_RPM` (default 25). On HTTP 429, honor `retry-after`
  and back off exponentially up to `LLM_MAX_RETRIES` (default 5). Timeouts via
  `LLM_TIMEOUT_S`.
- Disk cache (`data/llm_cache/`, SQLite) keyed by SHA-256 of
  `(model, messages, temperature, response_format)`. Temperature 0 for all calls.
  Cache hits are marked in usage records so latency and token figures distinguish
  cached from live calls. `LLM_CACHE=false` disables it.
- Missing `LLM_API_KEY`: the app starts, read endpoints work, ingestion and query
  return HTTP 503 with a message naming the variable. No fake output.
- Token usage from the provider's `usage` field is recorded per call. Estimated cost
  uses configurable per-million-token prices that default to 0 (free tier).

## 11. Evaluation

### 11.1 Corpus and questions

- `data/demo/`: the three smoke-test documents from section 1.
- `data/benchmark/`: the three demo documents plus about 9 more short fictional
  documents extending the same invented company (people, teams, projects, platforms,
  hardware, locations, vendors), written so several facts are only connected through
  shared entities across documents, plus distractor documents with overlapping
  vocabulary. Fictional, so the LLM cannot answer from prior knowledge. Small on
  purpose: about 12 chunks keeps extraction well inside the free daily token budget.
- `data/benchmark/questions.json`, at least 20 questions, categories:
  `direct`, `relationship`, `two_hop`, `three_hop`, `multi_document`,
  `insufficient_evidence`, `retrieval_trap`. Each question has: `id`, `question`,
  `category`, `reference_answer`, `answer_keywords` (list of alternatives per required
  fact), `required_documents`.
- The corpus and questions are written and committed in one commit before the first
  live evaluation run, and are not edited afterwards to improve scores. Any later change
  is committed with a reason in `docs/progress.md`, and earlier results stay recorded.
- Whatever the first live run produces is reported, including a mixed or negative
  result for GraphRAG. Retrieval code may be fixed for bugs found by the run; each fix
  applies to all modes and is logged with the before and after numbers.

### 11.2 Metrics (deterministic)

- Answer correctness: every required keyword group has at least one alternative
  present in the normalized answer. For `insufficient_evidence` questions: correct iff
  the system set `insufficient_evidence = true`.
- Token F1 between normalized answer and reference answer (SQuAD-style).
- Context recall: fraction of `required_documents` present among retrieved chunks.
- Citation precision: fraction of cited documents that are in `required_documents`.
  Citation recall: fraction of `required_documents` that were cited.
- Retrieval latency, end-to-end latency, prompt and completion tokens, cache-hit flag,
  estimated cost.
- No LLM judge in v1.

### 11.4 Free-tier budget

Rough per-run cost: ingestion is one extraction call per chunk (about 12 calls on the
70B model for the benchmark corpus); one evaluation pass is 20+ questions times 3 modes
times at most 2 calls (query-entity extraction is skipped for Standard RAG) on the 8B
model. If a daily limit is hit, the call fails with a clear rate-limit error after
retries, the run is marked `failed` with the reason, and a rerun the next day resumes
cheaply because completed calls are served from the cache. The extraction model is not
switched automatically; switching it changes the graph and must be a recorded decision.

### 11.3 Runner

- `POST /api/evaluation/run` runs every question in each selected mode against the
  currently indexed corpus as a background task, with progress pollable. Also runnable
  as `uv run python -m app.evaluation.runner`.
- No separate benchmark index. `POST /api/evaluation/load-corpus` uploads and ingests
  `data/benchmark/` (idempotent, by content hash). Each run records the set of indexed
  document ids in its config, and the run is flagged `corpus_mismatch` when the indexed
  set differs from the benchmark set, so extra user documents acting as distractors are
  visible rather than hidden.
- Results stored per run in SQLite; export as JSON and CSV.
- The UI shows which run it is displaying, its config, and whether results came from
  cached LLM calls.

## 12. API

From brief section 7:

- `POST /api/documents/upload` (multipart, one or more files; ingestion starts
  automatically)
- `GET /api/documents`, `GET /api/documents/{id}`, `DELETE /api/documents/{id}`
- `POST /api/documents/{id}/ingest`
- `GET /api/graph/stats`, `GET /api/graph/entities?q=&type=&limit=`,
  `GET /api/graph/entities/{id}`, `GET /api/graph/entities/{id}/neighbors?hops=1`
- `POST /api/query` with body `{question, mode: "standard" | "graph" | "hybrid",
  overrides?}`; each request is independent (no conversation state)
- `POST /api/evaluation/run`, `GET /api/evaluation/results` (latest run)

Additional:

- `POST /api/documents/{id}/ingest` (re-ingest), `GET /api/documents/{id}/chunks`,
  `GET /api/documents/{id}/errors`
- `GET /api/graph/search?q=` and `GET /api/graph/subgraph?limit=` for the explorer
- `GET /api/evaluation/runs/{run_id}`, `GET /api/evaluation/runs/{run_id}/export?format=csv|json`
- `GET /api/health` (Neo4j, Chroma, LLM key presence)
- `GET /api/stats`, `GET /api/activity`

Errors use one shape: `{"error": {"code": "...", "message": "..."}}`. Structured JSON
logging; API keys are never logged.

Ingestion runs as a FastAPI background task; document status is polled by the UI.

## 13. Frontend

Pages: Dashboard, Documents, Graph, Ask, Evaluation. Shared shell with sidebar
navigation, light and dark themes.

- Dashboard: four stat cards (documents, entities, relationships, chunks) with
  count-up, recent activity feed, service health.
- Documents: drag-and-drop upload, status badges with polling, chunk viewer, extraction
  error viewer, re-ingest and delete with confirmation.
- Graph: Cytoscape canvas, color and shape per entity type with legend, search box,
  click node for details panel (aliases, description, source chunks), click edge for
  relationship type, evidence and source document, expand neighbors.
- Ask: chat thread (display only; every question is answered independently, no
  follow-up context or query rewriting), mode selector (Standard / GraphRAG / Hybrid), and a "compare all
  modes" action that runs the same question in each mode side by side. Generated
  answer is visually separated from retrieved evidence. Citations are clickable chips
  that open the evidence; graph paths render as `A -[LEADS]-> B -[DEVELOPED]-> C`;
  retrieval details are collapsible (scores, retriever, rank, route).
- Evaluation: run benchmark with progress, summary table per mode, Recharts bar charts
  (accuracy, F1, context recall, citation precision/recall, latency), per-category
  breakdown, filterable per-question table, drill-down showing retrieved chunks, paths
  and answer for each mode, export buttons.

## 14. Testing

Unit (no network, no Docker):

- extraction validation: malformed JSON, missing fields, unknown types, dangling
  relations, unsupported evidence.
- normalization and entity resolution: alias merge, fuzzy threshold, no merge for
  distinct names.
- traversal: hop bound, degree guard, cycle avoidance, path ranking, against
  `InMemoryGraphStore`.
- fusion: RRF ordering, deduplication, budget cut, vector-only route.
- answer: citation parsing, invalid citation removal, ungrounded flag.
- metrics: keyword correctness, F1, recall, citation precision.

Integration:

- Full ingest-to-query on the demo corpus with `FakeLLM` (canned extraction and answer
  responses as fixtures), `InMemoryGraphStore`, ephemeral Chroma: verifies the graph
  contains the five Section 1 relations with provenance, GraphRAG retrieves all three
  documents for the Alice question, and re-ingest creates no duplicates.
- Neo4j store tests run against the Compose Neo4j when `NEO4J_TEST_URI` is set,
  otherwise skipped.

Manual live smoke test with Groq is documented in the README; its results are recorded
in `docs/progress.md`, not asserted in CI.

## 15. Deployment and setup

- `docker-compose.yml`: `neo4j` (with heap and page cache limited for a 16 GB laptop,
  persistent volume, health check), `backend`, `frontend`. Backend and frontend can
  also be run directly with `uv run` and `pnpm dev`.
- `.env.example` documents every variable; no secrets committed.
- README: architecture, prerequisites, setup, configuration, operating modes (Groq,
  Ollama or other OpenAI-compatible endpoints), API reference, demo walkthrough,
  benchmark, limitations, troubleshooting.

## 16. Documentation process

`docs/` holds: `design.md` (this file), `architecture.md`, `api.md`,
`configuration.md`, `evaluation.md`, `progress.md`. `progress.md` gets an entry for
every milestone: what was added, tests run with results, known issues. Docs are
updated in the same commit as the code they describe.

## 17. Milestones

1. Repository scaffold, Compose, config, docs skeleton, LLM provider with cache and
   rate limiting.
2. Ingestion: parsing, chunking, Chroma indexing, document registry and API.
3. Extraction, validation, normalization, Neo4j persistence, idempotent re-ingest.
4. Retrieval: standard, graph traversal, hybrid fusion; answer generation; query API.
5. Benchmark corpus, questions, metrics, runner, evaluation API.
6. Frontend: shell, dashboard, documents.
7. Frontend: graph explorer, ask page, evaluation dashboard.
8. Live run on Groq, record actual benchmark results, README and docs completion.

Each milestone ends with tests passing, docs updated, commit, push to `main`.

## 18. Decisions taken by the builder (not by the user)

- Python 3.11 instead of 3.12+ (installed version).
- Chroma embedded with its built-in ONNX MiniLM embedder instead of a separate
  embedding service.
- Groq as default provider through a generic OpenAI-compatible client; per-role model
  defaults as in section 10.
- Disk cache for LLM calls.
- Single `RELATES` relationship label with a `type` property.
- Traversal in Python over a store interface instead of one Cypher query.
- Entity identity by normalized name independent of type; conservative fuzzy merge.
- Equal evidence budget across modes.
- Deterministic keyword-based correctness, no LLM judge.
- Motion for animation; GSAP and Lenis not used.
- Cytoscape.js for the graph explorer.
- Benchmark corpus is a superset of the demo corpus; no separate benchmark index,
  mismatch flagged instead.
- Corpus and questions frozen in a commit before the first live run; any result is
  reported as measured.
- Single-turn question answering.

## 19. Open for the builder

- Exact prompt wording for extraction, query-entity extraction and answering.
- Exact thresholds after a first live run, provided changes are documented and applied
  identically to all modes.
- Visual design details of the frontend within the page specs above.
