# Loom

Loom is a GraphRAG system for multi-hop question answering. It builds a knowledge graph
from uploaded documents, answers questions by traversing entity relationships and
combining them with vector retrieval, and measures the result against a standard
vector-only RAG baseline on the same corpus, embeddings and LLM.

The motivating case: three documents state that Alice leads the Autonomous Systems team,
that the team developed Project Falcon which uses EdgeCore, and that EdgeCore is deployed
on NVIDIA Jetson. A question about "the hardware used by the project led by Alice's team"
shares little vocabulary with the third document, so similarity search tends to miss it.
Graph traversal reaches it through the shared entities.

Everything runs on free resources: the Groq free tier (or any OpenAI-compatible endpoint,
including a local Ollama server), CPU embeddings, Neo4j Community and ChromaDB.

## Status

| Component | State |
|---|---|
| Ingestion, extraction, graph construction | implemented, unit and integration tested |
| Standard, GraphRAG and Hybrid retrieval | implemented, tested with deterministic fixtures |
| Grounded answers with citation validation | implemented, tested |
| Benchmark corpus (11 documents, 22 questions), metrics, runner | implemented, tested |
| HTTP API | implemented, tested |
| Web UI | overview, documents, graph explorer, question answering and evaluation dashboard |
| Live benchmark results | not yet run; results will be published in `docs/evaluation.md` |

Progress is logged per milestone in [`docs/progress.md`](docs/progress.md).

## Architecture

```
                         +-------------------------------+
  Browser  ------------> |  Next.js frontend (port 3000) |
                         +---------------+---------------+
                                         | HTTP (JSON)
                         +---------------v---------------+
                         |  FastAPI backend (port 8000)  |
                         |                               |
   upload -------------> |  ingestion   parse, chunk     |
                         |  extraction  LLM JSON +       |
                         |              validation       |
                         |  resolution  entity merge     |
                         |  retrieval   standard | graph |
                         |              | hybrid (RRF)   |
                         |  answer      grounded JSON,   |
                         |              citation checks  |
                         |  evaluation  runner, metrics  |
                         +---+-----------+-----------+---+
                             |           |           |
                    +--------v--+  +-----v-----+  +--v----------------+
                    | Neo4j 5   |  | ChromaDB  |  | SQLite            |
                    | entities, |  | chunk and |  | documents, errors,|
                    | relations,|  | entity    |  | activity, eval    |
                    | provenance|  | vectors   |  | runs, LLM cache   |
                    +-----------+  +-----------+  +-------------------+
                                         |
                              +----------v----------+
                              | LLM provider        |
                              | Groq / Ollama / any |
                              | OpenAI-compatible   |
                              +---------------------+
```

### Ingestion

1. Validate the upload (extension allow-list, size limit, PDF magic bytes). The document
   id is a SHA-256 content hash, so the same file always maps to the same document.
2. Extract text per PDF page (pypdf) or from TXT and Markdown.
3. Chunk into overlapping character windows (`CHUNK_SIZE`, `CHUNK_OVERLAP`), breaking at
   paragraph or sentence boundaries. Chunks never span pages.
4. Embed chunks into ChromaDB.
5. Extract entities and relations per chunk with the LLM in JSON mode. The output is
   validated: unknown entity types become `OTHER`, relation types are normalized, and a
   relation is dropped (and logged as an extraction error) when an endpoint is not an
   extracted entity or its evidence sentence does not occur in the chunk.
6. Resolve entities against the graph by normalized name, alias, or a conservative fuzzy
   match, then upsert nodes, `MENTIONED_IN` links to chunk nodes, and `RELATES` edges whose
   provenance lists (`chunk_ids`, `document_ids`, `evidence`) record every supporting chunk.

Re-ingesting a document first removes its previous contribution, so repeated ingestion
creates no duplicate chunks, nodes or edges. A failed ingestion removes any partial data.

### Retrieval modes

| Mode | Evidence |
|---|---|
| Standard RAG | top-k chunks by cosine similarity. No graph access; a test enforces that the module imports nothing from the graph package. |
| GraphRAG | query entities (LLM plus a name scan of the question) resolved to seed nodes; breadth-first traversal up to `MAX_HOPS` (default 3, cap 4), high-degree nodes not expanded, at most `MAX_PATHS`; paths scored by similarity between the question and each edge's fact text with hop decay; evidence is the chunks behind the top paths plus chunks mentioning each path's end node. |
| Hybrid GraphRAG | weighted reciprocal rank fusion of both rankings, deduplicated by chunk. Falls back to vector results, and reports `route = vector_only` with the reason, when the graph contributes nothing. |

All modes share one evidence budget (`MAX_EVIDENCE_CHUNKS`, default 6), the same answer
model and the same prompt.

### Grounded answers

The answer prompt lists evidence blocks `[S1]..[Sn]` (filename, page, chunk id, text) and
graph facts `[P1]..[Pm]` (rendered paths such as
`Alice -[LEADS]-> Autonomous Systems -[DEVELOPED]-> Project Falcon`). The model returns
JSON with `answer`, `explanation`, `citations`, `insufficient_evidence` and `conflicts`.
Citations that do not refer to a block in the prompt are removed and reported. An answer
without any valid citation that does not declare insufficient evidence is flagged
`grounded: false`. Loom never labels an answer as verified.

## Prerequisites

| Requirement | Version | Used for |
|---|---|---|
| Python | 3.11 or newer | backend |
| uv | 0.4 or newer | Python dependencies |
| Node.js | 20 or newer | frontend |
| pnpm | 9 or newer | frontend dependencies |
| Docker with Compose | 24 or newer | Neo4j (and optionally the whole stack) |
| Groq API key | free tier | extraction and answers (optional at install time) |

About 2 GB of RAM is used by Neo4j with the bundled limits. The ONNX embedding model
(about 80 MB) is downloaded on first use.

## Setup

```bash
git clone https://github.com/yatinannam/Loom.git
cd Loom
cp .env.example .env          # then set LLM_API_KEY
```

### Option A: services locally, Neo4j in Docker

```bash
docker compose up -d neo4j

cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# in a second terminal
cd frontend
pnpm install
pnpm dev                      # http://localhost:3000
```

### Option B: everything in Docker

```bash
docker compose up --build
```

The API is at `http://localhost:8000` (OpenAPI docs at `/docs`), Neo4j Browser at
`http://localhost:7474`.

## Configuration

All settings are environment variables, read from `.env` at the repository root. The
full list with defaults is in [`.env.example`](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | empty | provider key; without it, ingestion and querying return HTTP 503 |
| `EXTRACTION_MODEL` | `llama-3.3-70b-versatile` | entity and relation extraction |
| `ANSWER_MODEL` | `llama-3.1-8b-instant` | answer generation, same for every mode |
| `QUERY_ENTITY_MODEL` | `llama-3.1-8b-instant` | entity mentions in questions |
| `LLM_MAX_RPM` | `25` | client-side request throttle |
| `LLM_CACHE` | `true` | SQLite cache of LLM responses keyed by request hash |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | ONNX on CPU; other names load sentence-transformers |
| `MAX_HOPS` | `3` | traversal depth (1 to 4) |
| `MAX_EVIDENCE_CHUNKS` | `6` | evidence budget shared by all modes |
| `VECTOR_WEIGHT`, `GRAPH_WEIGHT` | `1.0` | RRF weights for hybrid mode |

### Operating modes

| Mode | Settings | Notes |
|---|---|---|
| Groq free tier (default) | `LLM_API_KEY` from console.groq.com | Free limits apply per model and per day. Check current quotas in the Groq console. |
| Local Ollama | `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_API_KEY=ollama`, model names such as `qwen2.5:3b` | No network or key; slow on CPU-only machines, and small models extract less reliably. |
| Other OpenAI-compatible providers | set `LLM_BASE_URL`, `LLM_API_KEY` and model names | Any `/chat/completions` endpoint with JSON mode. |

There is no fallback to fabricated output. If the provider is unreachable or rate limited
after retries, the request fails with a typed error (`llm_unavailable`,
`llm_rate_limited`) and ingestion marks the document `failed` with the reason.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Neo4j reachability, LLM key presence, models |
| GET | `/api/stats` | document, chunk, entity and relation counts |
| GET | `/api/activity` | recent ingestion, query and evaluation events |
| POST | `/api/documents/upload` | multipart `files`; ingestion runs in the background |
| GET | `/api/documents` | all documents with status and counts |
| GET | `/api/documents/{id}` | one document |
| DELETE | `/api/documents/{id}` | remove a document and its graph contribution |
| POST | `/api/documents/{id}/ingest` | re-ingest |
| GET | `/api/documents/{id}/chunks` | stored chunks |
| GET | `/api/documents/{id}/errors` | extraction warnings and errors |
| GET | `/api/graph/stats` | entity and relation counts by type |
| GET | `/api/graph/entities?q=&type=&limit=` | list or filter entities |
| GET | `/api/graph/search?q=` | entity search by name or alias |
| GET | `/api/graph/entities/{id}` | entity with mentions and relations |
| GET | `/api/graph/entities/{id}/neighbors?hops=1` | neighborhood (1 or 2 hops) |
| GET | `/api/graph/subgraph?limit=` | highest-degree entities and the relations between them |
| POST | `/api/query` | `{"question", "mode": "standard" \| "graph" \| "hybrid", "overrides"?}` |
| POST | `/api/evaluation/load-corpus` | upload and ingest `data/benchmark/` |
| POST | `/api/evaluation/run` | `{"modes": [...]}`; runs in the background |
| GET | `/api/evaluation/runs` | all runs |
| GET | `/api/evaluation/runs/{id}` | run config, summary and progress |
| GET | `/api/evaluation/runs/{id}/results` | per-question records |
| GET | `/api/evaluation/results` | latest run with records |
| GET | `/api/evaluation/runs/{id}/export?format=csv\|json` | download results |

Errors share one shape: `{"error": {"code": "...", "message": "..."}}`.

## Demo walkthrough

1. Start the stack and open `http://localhost:3000`.
2. On Documents, upload the three files in `data/demo/`.
3. On Graph, inspect the extracted entities and relationships; click an edge to see its
   evidence sentence and source document.
4. On Ask, enter: "Which hardware platform is used by the project led by Alice's team,
   and which technology connects the project to that hardware?" and compare the three
   modes. Each answer shows its citations, retrieved chunks with retriever ranks, and the
   graph paths that contributed.
5. On Evaluation, load the benchmark corpus and run all modes.

## Benchmark

`data/benchmark/` holds 11 fictional documents and 22 questions in seven categories
(direct, relationship, two-hop, three-hop, multi-document, insufficient evidence,
retrieval traps). Metrics are deterministic: keyword-group answer correctness, token F1,
context recall over required documents, citation precision and recall, and latency.
There is no LLM judge. Details and integrity rules are in
[`docs/evaluation.md`](docs/evaluation.md).

```bash
cd backend
uv run python -m app.evaluation.runner --load-corpus --modes standard graph hybrid
```

The corpus and questions were frozen in a commit before any live run. Published numbers
come only from actual runs.

## Tests

```bash
cd backend
uv run pytest
```

Tests use deterministic fakes (a canned-response LLM, a hashing embedder, an in-memory
graph store, an ephemeral Chroma client) and make no network calls. They cover upload
validation, chunking, extraction validation, entity resolution, graph store semantics,
idempotent ingestion and removal, traversal bounds, fusion, citation handling, metrics,
the runner and the HTTP API.

Neo4j store tests run against a live database when `NEO4J_TEST_URI` is set:

```bash
docker compose up -d neo4j
NEO4J_TEST_URI=bolt://localhost:7687 uv run pytest tests/test_graph_store.py
```

## Repository layout

```
backend/app/
  api/           HTTP routes and error mapping
  ingestion/     parsing, chunking, pipeline
  extraction/    schema, normalization, LLM extraction
  graph/         store interface, Neo4j and in-memory stores, resolution, traversal
  vector/        Chroma store and embedders
  llm/           OpenAI-compatible client, cache
  retrieval/     standard, graph, hybrid, fusion
  answer/        grounded answer generation
  evaluation/    dataset, metrics, runner
backend/tests/   unit and integration tests, fixtures
frontend/        Next.js application
data/demo/       three-document smoke corpus
data/benchmark/  benchmark corpus and questions
docs/            brief, design, plan, progress log, evaluation
```

## Limitations

- Extraction quality depends on the LLM. Small local models miss relations and produce
  more malformed output; validation drops unsupported relations instead of repairing them.
- Entity resolution is conservative: different names for the same thing that are neither
  aliases nor near-identical strings remain separate nodes.
- Scanned PDFs without a text layer are rejected; there is no OCR.
- Single-user, no authentication. Not intended for exposure on a public network.
- The benchmark corpus is small and synthetic. It isolates the multi-hop retrieval
  problem; it does not represent performance on real-world corpora.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/api/health` reports `neo4j: down` | Neo4j is not running or the credentials differ. Run `docker compose up -d neo4j` and check `NEO4J_*` in `.env`. |
| Upload returns 503 `llm_not_configured` | `LLM_API_KEY` is empty. Set it in `.env` and restart the backend. |
| Documents end in `failed` with `llm_rate_limited` | The provider's free limit was reached. Wait for the window to reset and re-ingest; completed calls are served from the cache. |
| First ingestion is slow | The ONNX embedding model is being downloaded (about 80 MB). |
| Frontend shows "Cannot reach the API" | The backend is not on `http://localhost:8000`. Set `NEXT_PUBLIC_API_URL` for the frontend if it runs elsewhere. |

## Documentation

- [`docs/brief.md`](docs/brief.md): original requirements
- [`docs/design.md`](docs/design.md): design and decisions
- [`docs/architecture.md`](docs/architecture.md): data model, algorithms, failure handling
- [`docs/plan.md`](docs/plan.md): implementation plan
- [`docs/progress.md`](docs/progress.md): milestone log with test results
- [`docs/evaluation.md`](docs/evaluation.md): benchmark method and results
