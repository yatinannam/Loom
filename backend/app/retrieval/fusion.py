"""Weighted reciprocal rank fusion of chunk rankings."""

from dataclasses import replace

from app.retrieval.types import RetrievedChunk


def rrf_fuse(
    rankings: dict[str, list[RetrievedChunk]], weights: dict[str, float], k: int, limit: int
) -> list[RetrievedChunk]:
    """score(chunk) = sum over retrievers of weight / (k + rank). Chunks returned by
    several retrievers are merged and keep every retriever's rank in `sources`."""
    fused: dict[str, RetrievedChunk] = {}
    for name, items in rankings.items():
        weight = weights.get(name, 1.0)
        for rank, item in enumerate(items, start=1):
            contribution = weight / (k + rank)
            if item.chunk.id in fused:
                existing = fused[item.chunk.id]
                existing.score += contribution
                existing.sources.update(item.sources)
            else:
                fused[item.chunk.id] = replace(item, score=contribution, sources=dict(item.sources))
    return sorted(fused.values(), key=lambda c: -c.score)[:limit]
