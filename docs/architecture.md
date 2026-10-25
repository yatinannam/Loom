# Architecture

This document describes the data model and algorithms in more depth than the README.
Setup, configuration and the API summary are in the README; the interactive API
reference is served by FastAPI at `/docs`.

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `app/config.py` | settings from environment and `.env` | pydantic-settings |
| `app/llm/provider.py` | OpenAI-compatible chat client: throttle, retries, typed errors | httpx, `llm/cache.py` |
| `app/llm/cache.py` | SQLite response cache keyed by request hash | sqlite3 |
| `app/ingestion/parsing.py` | upload validation, content-hash ids, text extraction | pypdf |
| `app/ingestion/chunking.py` | overlapping chunks on paragraph or sentence boundaries | |
| `app/ingestion/pipeline.py` | end-to-end ingestion and removal | all stores, extraction, resolution |
| `app/extraction/*` | extraction schema, prompt, validation, name normalization | LLM provider |
| `app/graph/store.py` | `GraphStore` protocol and data types | |
| `app/graph/neo4j_store.py` | Neo4j implementation | neo4j driver |
| `app/graph/memory_store.py` | in-process implementation for tests | |
| `app/graph/lazy.py` | connect-on-first-use proxy with retry cooldown | |
| `app/graph/resolution.py` | entity resolution for ingestion and queries | graph and vector stores |
| `app/graph/traversal.py` | bounded path enumeration and scoring | graph store |
| `app/vector/store.py` | Chroma store for chunks and entity names; embedders | chromadb |
| `app/retrieval/standard.py` | vector-only baseline | vector store only |
| `app/retrieval/graph.py` | GraphRAG retrieval | resolution, traversal, stores, LLM |
| `app/retrieval/fusion.py`, `hybrid.py` | weighted RRF and the hybrid mode | both retrievers |
| `app/answer/generator.py` | grounded answer prompt, parsing, citation validation | LLM provider |
| `app/query.py` | mode dispatch, timings, usage accounting | retrievers, answer |
| `app/evaluation/*` | dataset, metrics, runner | query service, registry |
| `app/registry.py` | documents, extraction errors, activity, evaluation runs | sqlite3 |
| `app/api/*` | HTTP routes and error mapping | services |

Every external system sits behind a protocol (`LLMProvider`, `Embedder`, `VectorStore`,
`GraphStore`). Tests substitute deterministic implementations; application code never
imports test doubles.

## Storage

### Neo4j

```
(:Entity {id, name, type, aliases: [str], description, norm, search: [str], degree})
(:Chunk  {id, document_id, filename, page})
(:Entity)-[:MENTIONED_IN]->(:Chunk)
(:Entity)-[:RELATES {type, chunk_ids: [str], document_ids: [str], evidence: [str], confidence}]->(:Entity)
```

- Unique constraints on `Entity.id` and `Chunk.id`; index on `Chunk.document_id`.
- `RELATES` is a single relationship label with a `type` property. Neo4j cannot
  parameterize relationship labels, and a single label keeps every statement
  parameterized.
- One edge per `(source, type, target)`. Provenance lists are parallel: index `i` of
  `chunk_ids`, `document_ids` and `evidence` describes one supporting chunk. A chunk is
  appended at most once.
- `degree` is recomputed after every ingest and removal and is used by the traversal's
  high-degree guard.

### ChromaDB

Two cosine collections per embedding model (`{model-slug}-chunks`,
`{model-slug}-entities`). Changing `EMBEDDING_MODEL` therefore starts fresh collections
instead of mixing vector dimensions. Chunk metadata: `document_id`, `filename`, `page`
(`-1` for none), `chunk_index`, `char_start`, `char_end`. Entity documents are
`"{name}: {description}"`.

### SQLite

`data/runtime/loom.db` holds the document registry, extraction errors, the activity
feed and evaluation runs with one JSON record per question and mode.
`data/runtime/llm_cache.db` holds cached LLM responses.

## Identity and idempotency

- `document_id` = first 16 hex characters of SHA-256 of the file bytes.
- `chunk_id` = `{document_id}:{chunk_index}`.
- `entity_id` = normalized name with spaces replaced by hyphens. Normalization: Unicode
  NFKC, lowercase, punctuation to spaces, whitespace collapsed, leading "the" removed.

Ingestion starts by removing the document's previous contribution: its chunks from
Chroma; its chunk ids from every edge's provenance (edges left without provenance are
deleted); its chunk nodes; then entities with no remaining mention. Ingesting the same
document twice therefore yields the same graph and index. A failure at any point runs
the same removal, so a failed document leaves nothing behind.

## Entity resolution

Ingestion merges a newly extracted entity into an existing node when its normalized
name or any alias equals an existing name or alias, or when the difflib ratio of the
normalized names is at least 0.92. The threshold is deliberately high: a missed merge
costs one hop, a wrong merge invents a connection between unrelated facts.

Queries resolve mentions with decreasing confidence: exact name (1.0), alias (0.95),
fuzzy ratio of at least 0.85, then nearest neighbor in the entity-name collection above
`ENTITY_MIN_SCORE`. Independently, the question text is scanned for every known name
and alias as whole words (0.9). The best match per entity is kept and the top
`MAX_SEED_ENTITIES` become seeds.

## Traversal and path scoring

```
frontier = seeds
for hop in 1..MAX_HOPS:
    expandable = frontier nodes that are seeds or have degree <= MAX_NODE_DEGREE
    edges = graph.neighbors(expandable)          # both directions
    extend every frontier path by every edge to an unvisited node
    stop when MAX_PATHS paths exist
```

Each edge is rendered as fact text, `"{source} {type as words} {target}: {evidence}"`,
and embedded together with the question in one batch. A path's score is the mean cosine
similarity between the question and its edges, multiplied by `HOP_DECAY^(hops - 1)`,
plus 0.1 when the path ends on a different seed than it started from. Paths below
`PATH_MIN_SCORE` are discarded and the top `TOP_PATHS` kept.

Evidence chunks are those in the provenance of the kept paths' edges, plus chunks that
mention each kept path's end node. The second set brings in facts one hop beyond the
traversal bound: in the demo, NVIDIA Jetson is four hops from Alice, and with
`MAX_HOPS = 3` the technology document still enters through its mention of EdgeCore.
Chunks are ranked by the best score of any path that contributed them and cut to
`MAX_EVIDENCE_CHUNKS`.

## Hybrid fusion

`score(chunk) = sum over retrievers r of weight_r / (RRF_K + rank_r(chunk))`. Chunks
found by both retrievers are merged and keep both ranks in `sources`, which the UI shows
per evidence block. When graph retrieval returns no chunks, hybrid returns the vector
results with `route = "vector_only"` and the graph's reason.

## Answer validation

The model sees evidence as `[S#]` blocks and graph paths as `[P#]` facts, each path
annotated with the `[S#]` blocks that support it. After the reply:

- citation ids are normalized (`[s2]` becomes `S2`); ids outside the prompt move to
  `invalid_citations`;
- `grounded` is false when no valid citation remains and the model did not declare
  insufficient evidence;
- an empty retrieval skips the LLM and returns an insufficient-evidence answer.

## Failure handling

| Condition | Behavior |
|---|---|
| Neo4j down at startup | API starts; graph-dependent endpoints return 503 `graph_unavailable`; reconnection is attempted at most every 10 s |
| No `LLM_API_KEY` | read endpoints work; upload, re-ingest and corpus loading return 503 `llm_not_configured`; queries that miss the cache return the same |
| HTTP 429 from the provider | `retry-after` honored, exponential backoff up to `LLM_MAX_RETRIES`, then `llm_rate_limited` (HTTP 429) |
| 5xx or network error | retried, then `llm_unavailable` (HTTP 503) |
| Malformed extraction JSON | one retry with the parse error; then the chunk is skipped and the error recorded |
| Unsupported relation | dropped and recorded as an extraction error |
| Unexpected exception | HTTP 500 `internal_error`; details are logged, not returned |
