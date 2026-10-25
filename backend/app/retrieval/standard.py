"""Standard RAG baseline: vector similarity only. Deliberately has no graph imports."""

import time

from app.config import Settings
from app.retrieval.types import RetrievalResult, RetrievedChunk
from app.vector.store import VectorStore


def retrieve_standard(vector: VectorStore, question: str, settings: Settings) -> RetrievalResult:
    start = time.perf_counter()
    hits = vector.search(question, k=settings.max_evidence_chunks, min_score=settings.vector_min_score)
    chunks = [
        RetrievedChunk(chunk=h.chunk, score=h.score, sources={"vector": {"rank": i + 1, "score": h.score}})
        for i, h in enumerate(hits)
    ]
    return RetrievalResult(
        mode="standard",
        chunks=chunks,
        route="vector",
        route_reason="vector similarity search" if chunks else "no chunk above VECTOR_MIN_SCORE",
        latency_ms=(time.perf_counter() - start) * 1000,
    )
