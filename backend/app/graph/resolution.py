"""Entity resolution for ingestion (merge into existing nodes) and for queries
(map question mentions to seed nodes)."""

import difflib
from dataclasses import dataclass
from typing import Literal

from app.extraction.normalize import normalize_name
from app.graph.store import GraphStore
from app.vector.store import VectorStore

QUERY_FUZZY_THRESHOLD = 0.85
MIN_SCAN_KEY_LENGTH = 3
METHOD_SCORES = {"exact": 1.0, "alias": 0.95, "scan": 0.9}


@dataclass
class SeedMatch:
    entity_id: str
    mention: str
    score: float
    method: Literal["exact", "alias", "fuzzy", "embedding", "scan"]


class EntityResolver:
    def __init__(self, graph: GraphStore, vector: VectorStore, fuzzy_threshold: float = 0.92):
        self.graph = graph
        self.vector = vector
        self.fuzzy_threshold = fuzzy_threshold
        self._keys: dict[str, tuple[str, bool]] = {}  # normalized form -> (entity id, is primary name)

    def refresh(self) -> None:
        self._keys = {}
        for id, names in self.graph.entity_index():
            self.register(id, names)

    def register(self, id: str, names: list[str]) -> None:
        for i, name in enumerate(names):
            key = normalize_name(name)
            if key and (key not in self._keys or (i == 0 and not self._keys[key][1])):
                self._keys[key] = (id, i == 0)

    def _fuzzy(self, key: str, threshold: float) -> tuple[str, float] | None:
        best = difflib.get_close_matches(key, list(self._keys), n=1, cutoff=threshold)
        if not best:
            return None
        return self._keys[best[0]][0], difflib.SequenceMatcher(None, key, best[0]).ratio()

    def resolve_ingest(self, name: str, aliases: list[str]) -> str | None:
        forms = [normalize_name(f) for f in [name, *aliases]]
        for key in forms:
            if key in self._keys:
                return self._keys[key][0]
        match = self._fuzzy(forms[0], self.fuzzy_threshold)
        return match[0] if match else None

    def resolve_query(self, mentions: list[str], question: str, min_score: float, limit: int) -> list[SeedMatch]:
        self.refresh()
        found: dict[str, SeedMatch] = {}

        def offer(match: SeedMatch) -> None:
            if match.entity_id not in found or match.score > found[match.entity_id].score:
                found[match.entity_id] = match

        for mention in mentions:
            key = normalize_name(mention)
            if not key:
                continue
            if key in self._keys:
                id, primary = self._keys[key]
                method = "exact" if primary else "alias"
                offer(SeedMatch(id, mention, METHOD_SCORES[method], method))
                continue
            fuzzy = self._fuzzy(key, QUERY_FUZZY_THRESHOLD)
            if fuzzy:
                offer(SeedMatch(fuzzy[0], mention, fuzzy[1], "fuzzy"))
                continue
            for id, score in self.vector.search_entities(mention, k=1):
                if score >= min_score:
                    offer(SeedMatch(id, mention, score, "embedding"))

        padded = f" {normalize_name(question)} "
        for key, (id, _) in self._keys.items():
            if len(key) >= MIN_SCAN_KEY_LENGTH and f" {key} " in padded:
                offer(SeedMatch(id, key, METHOD_SCORES["scan"], "scan"))

        return sorted(found.values(), key=lambda s: -s.score)[:limit]
