"""GraphRAG retrieval: query entities -> seed nodes -> bounded traversal -> ranked
paths -> supporting chunks."""

import json
import logging
import time

from app.config import Settings
from app.graph.resolution import EntityResolver
from app.graph.store import GraphStore
from app.graph.traversal import enumerate_paths, score_paths
from app.llm.provider import LLMProvider, LLMUsage
from app.retrieval.types import GraphPath, PathStep, RetrievalResult, RetrievedChunk
from app.vector.store import VectorStore

log = logging.getLogger(__name__)

QUERY_ENTITY_PREFIX = "List the entities mentioned in this question:"
QUERY_ENTITY_SYSTEM = (
    "You identify the entities a question refers to: people, organizations, teams, projects, "
    "products, technologies, places and events. Return JSON {\"entities\": [\"...\"]} using the "
    "wording of the question. Return an empty list if it names none."
)


def query_entities(llm: LLMProvider, model: str, question: str) -> tuple[list[str], LLMUsage]:
    resp = llm.complete(
        [{"role": "system", "content": QUERY_ENTITY_SYSTEM},
         {"role": "user", "content": f"{QUERY_ENTITY_PREFIX}\n{question}"}],
        model=model,
        json_mode=True,
        max_tokens=256,
    )
    try:
        items = json.loads(resp.text).get("entities") or []
        mentions = [str(i).strip() for i in items if str(i).strip()]
    except (json.JSONDecodeError, AttributeError):
        log.warning("query entity response was not valid JSON; falling back to name scan only")
        mentions = []
    return mentions, resp.usage


def _fact_text(rel, names: dict[str, str]) -> str:
    verb = rel.type.replace("_", " ").lower()
    evidence = rel.evidence[0] if rel.evidence else ""
    return f"{names.get(rel.source, rel.source)} {verb} {names.get(rel.target, rel.target)}: {evidence}"


def retrieve_graph(
    question: str,
    *,
    llm: LLMProvider,
    vector: VectorStore,
    graph: GraphStore,
    resolver: EntityResolver,
    settings: Settings,
) -> RetrievalResult:
    start = time.perf_counter()

    def result(reason: str, chunks=(), paths=(), seeds=(), usage=()) -> RetrievalResult:
        return RetrievalResult(
            mode="graph", chunks=list(chunks), paths=list(paths), seeds=list(seeds), route="graph",
            route_reason=reason, latency_ms=(time.perf_counter() - start) * 1000, usage=list(usage),
        )

    mentions, usage = query_entities(llm, settings.query_entity_model, question)
    seeds = resolver.resolve_query(mentions, question, settings.entity_min_score, settings.max_seed_entities)
    if not seeds:
        return result("no query entity matched a graph node", usage=[usage])
    seed_ids = [s.entity_id for s in seeds]

    raw_paths = enumerate_paths(graph, seed_ids, settings.max_hops, settings.max_node_degree, settings.max_paths)
    if not raw_paths:
        return result("seed entities have no relations", seeds=seeds, usage=[usage])

    edges = {rel.key: rel for path in raw_paths for rel, _ in path}
    node_ids = sorted({n for rel in edges.values() for n in (rel.source, rel.target)})
    names = {e.id: e.name for e in graph.get_entities(node_ids)}
    keys = list(edges)
    vecs = vector.embed([question] + [_fact_text(edges[k], names) for k in keys])
    edge_vecs = dict(zip(keys, vecs[1:]))
    scored = score_paths(raw_paths, vecs[0], edge_vecs, settings.hop_decay, seed_ids,
                         settings.path_min_score, settings.top_paths)
    if not scored:
        return result("no path scored above PATH_MIN_SCORE", seeds=seeds, usage=[usage])

    paths: list[GraphPath] = []
    chunk_scores: dict[str, float] = {}
    terminal_scores: dict[str, float] = {}
    for path, score in scored:
        steps = [PathStep(r.source, names.get(r.source, r.source), r.type, r.target, names.get(r.target, r.target), f)
                 for r, f in path]
        chunk_ids = list(dict.fromkeys(c for r, _ in path for c in r.chunk_ids))
        paths.append(GraphPath(steps=steps, score=score, chunk_ids=chunk_ids))
        for c in chunk_ids:
            chunk_scores[c] = max(chunk_scores.get(c, 0.0), score)
        last = steps[-1]
        terminal = last.target_id if last.forward else last.source_id
        terminal_scores[terminal] = max(terminal_scores.get(terminal, 0.0), score)

    # Chunks mentioning a path's end node carry facts one hop beyond the traversal bound.
    for entity, mentions_list in graph.mentions(sorted(terminal_scores)).items():
        for m in mentions_list:
            chunk_scores.setdefault(m.chunk_id, terminal_scores[entity])

    ranked = sorted(chunk_scores.items(), key=lambda kv: -kv[1])[: settings.max_evidence_chunks]
    records = {c.id: c for c in vector.get_chunks([cid for cid, _ in ranked])}
    chunks = [
        RetrievedChunk(chunk=records[cid], score=s, sources={"graph": {"rank": i + 1, "score": s}})
        for i, (cid, s) in enumerate((cid, s) for cid, s in ranked if cid in records)
    ]
    return result(f"{len(paths)} paths from {len(seeds)} seed entities", chunks, paths, seeds, [usage])
