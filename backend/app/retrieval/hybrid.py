"""Hybrid GraphRAG: vector and graph retrieval fused with weighted RRF. Falls back
to vector results when the graph contributes nothing."""

import time

from app.retrieval.fusion import rrf_fuse
from app.retrieval.graph import retrieve_graph
from app.retrieval.standard import retrieve_standard
from app.retrieval.types import RetrievalResult


def retrieve_hybrid(question: str, *, llm, vector, graph, resolver, settings) -> RetrievalResult:
    start = time.perf_counter()
    vec = retrieve_standard(vector, question, settings)
    gra = retrieve_graph(question, llm=llm, vector=vector, graph=graph, resolver=resolver, settings=settings)
    if not gra.chunks:
        chunks, route, reason = vec.chunks, "vector_only", f"graph contributed nothing ({gra.route_reason})"
    else:
        chunks = rrf_fuse(
            {"vector": vec.chunks, "graph": gra.chunks},
            weights={"vector": settings.vector_weight, "graph": settings.graph_weight},
            k=settings.rrf_k,
            limit=settings.max_evidence_chunks,
        )
        route, reason = "hybrid", f"RRF of {len(vec.chunks)} vector and {len(gra.chunks)} graph chunks"
    return RetrievalResult(
        mode="hybrid",
        chunks=chunks,
        paths=gra.paths,
        seeds=gra.seeds,
        route=route,
        route_reason=reason,
        latency_ms=(time.perf_counter() - start) * 1000,
        usage=gra.usage,
    )
