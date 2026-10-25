"""Retrieval result types shared by all modes."""

from dataclasses import dataclass, field

from app.graph.resolution import SeedMatch
from app.llm.provider import LLMUsage
from app.models import ChunkRecord


@dataclass
class PathStep:
    """One edge on a path. source/target follow the stored edge direction;
    `forward` says whether the traversal followed it source to target."""

    source_id: str
    source_name: str
    type: str
    target_id: str
    target_name: str
    forward: bool


@dataclass
class GraphPath:
    steps: list[PathStep]
    score: float
    chunk_ids: list[str]

    def render(self) -> str:
        first = self.steps[0]
        parts = [first.source_name if first.forward else first.target_name]
        for s in self.steps:
            parts.append(f"-[{s.type}]-> {s.target_name}" if s.forward else f"<-[{s.type}]- {s.source_name}")
        return " ".join(parts)


@dataclass
class RetrievedChunk:
    chunk: ChunkRecord
    score: float
    sources: dict[str, dict]


@dataclass
class RetrievalResult:
    mode: str
    chunks: list[RetrievedChunk]
    paths: list[GraphPath] = field(default_factory=list)
    seeds: list[SeedMatch] = field(default_factory=list)
    route: str = ""
    route_reason: str = ""
    latency_ms: float = 0.0
    usage: list[LLMUsage] = field(default_factory=list)
