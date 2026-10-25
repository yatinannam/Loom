"""Graph store interface and data types."""

from dataclasses import dataclass, field
from typing import Protocol


class GraphUnavailable(Exception):
    code = "graph_unavailable"


@dataclass
class Entity:
    id: str
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    degree: int = 0


@dataclass
class Relation:
    source: str
    target: str
    type: str
    chunk_ids: list[str]
    document_ids: list[str]
    evidence: list[str]
    confidence: float

    @property
    def key(self) -> str:
        return f"{self.source}|{self.type}|{self.target}"


@dataclass(frozen=True)
class Mention:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None


class GraphStore(Protocol):
    def upsert_entity(self, entity: Entity, mention: Mention) -> None: ...
    def upsert_relation(
        self, source_id: str, target_id: str, type: str, mention: Mention, evidence: str, confidence: float
    ) -> None: ...
    def get_entity(self, id: str) -> Entity | None: ...
    def get_entities(self, ids: list[str]) -> list[Entity]: ...
    def find_entities(self, q: str | None, type: str | None, limit: int) -> list[Entity]: ...
    def entity_index(self) -> list[tuple[str, list[str]]]: ...
    def neighbors(self, ids: list[str]) -> list[Relation]: ...
    def mentions(self, ids: list[str]) -> dict[str, list[Mention]]: ...
    def remove_document(self, document_id: str) -> list[str]: ...
    def recompute_degrees(self) -> None: ...
    def stats(self) -> dict: ...
    def subgraph(self, limit: int) -> tuple[list[Entity], list[Relation]]: ...
    def clear(self) -> None: ...


def merge_aliases(name: str, existing: list[str], new: list[str]) -> list[str]:
    out: list[str] = []
    for alias in [*existing, *new]:
        if alias != name and alias not in out:
            out.append(alias)
    return out
