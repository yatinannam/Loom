"""Query service: retrieval in the requested mode, then grounded answer generation."""

import time
from dataclasses import dataclass

from app.answer.generator import Answer, generate_answer
from app.config import Settings
from app.graph.store import GraphUnavailable
from app.retrieval.graph import retrieve_graph
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.standard import retrieve_standard
from app.retrieval.types import RetrievalResult

MODES = ("standard", "graph", "hybrid")

# Settings a single query may override; everything else (keys, models, storage) is fixed.
OVERRIDABLE = {
    "max_evidence_chunks", "vector_min_score", "entity_min_score", "max_seed_entities", "max_hops",
    "max_node_degree", "max_paths", "hop_decay", "path_min_score", "top_paths", "rrf_k",
    "vector_weight", "graph_weight",
}


@dataclass
class QueryResponse:
    question: str
    mode: str
    answer: Answer
    retrieval: RetrievalResult
    timings: dict
    usage: dict


class QueryService:
    def __init__(self, llm, vector, graph, resolver, settings: Settings, registry):
        self.llm = llm
        self.vector = vector
        self.graph = graph
        self.resolver = resolver
        self.settings = settings
        self.registry = registry

    def _settings(self, overrides: dict | None) -> Settings:
        if not overrides:
            return self.settings
        unknown = set(overrides) - OVERRIDABLE
        if unknown:
            raise ValueError(f"settings not overridable per query: {sorted(unknown)}")
        return Settings(_env_file=None, **{**self.settings.model_dump(), **overrides})

    def retrieve(self, question: str, mode: str, settings: Settings) -> RetrievalResult:
        if mode == "standard":
            return retrieve_standard(self.vector, question, settings)
        if self.graph is None:
            raise GraphUnavailable("graph store is not connected; only standard mode is available")
        deps = dict(llm=self.llm, vector=self.vector, graph=self.graph, resolver=self.resolver, settings=settings)
        if mode == "graph":
            return retrieve_graph(question, **deps)
        if mode == "hybrid":
            return retrieve_hybrid(question, **deps)
        raise ValueError(f"unknown mode {mode!r}; use one of {MODES}")

    def run(self, question: str, mode: str, overrides: dict | None = None) -> QueryResponse:
        settings = self._settings(overrides)
        start = time.perf_counter()
        retrieval = self.retrieve(question, mode, settings)
        retrieved_at = time.perf_counter()
        answer = generate_answer(self.llm, settings.answer_model, question, retrieval)
        end = time.perf_counter()

        calls = [*retrieval.usage, *([answer.usage] if answer.usage else [])]
        prompt = sum(u.prompt_tokens for u in calls)
        completion = sum(u.completion_tokens for u in calls)
        usage = {
            "llm_calls": len(calls),
            "cached_calls": sum(1 for u in calls if u.cached),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "estimated_cost_usd": (prompt * settings.price_input_per_mtok + completion * settings.price_output_per_mtok) / 1e6,
        }
        if self.registry is not None:
            self.registry.log_activity("query", f"[{mode}] {question[:120]}")
        return QueryResponse(
            question=question,
            mode=mode,
            answer=answer,
            retrieval=retrieval,
            timings={
                "retrieval_ms": (retrieved_at - start) * 1000,
                "generation_ms": (end - retrieved_at) * 1000,
                "total_ms": (end - start) * 1000,
            },
            usage=usage,
        )
