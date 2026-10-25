"""In-process graph store. Used by tests; same semantics as the Neo4j store."""

from collections import Counter
from dataclasses import replace

from app.extraction.normalize import normalize_name
from app.graph.store import Entity, Mention, Relation, merge_aliases


class InMemoryGraphStore:
    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._mentions: dict[str, list[Mention]] = {}
        self._relations: dict[str, Relation] = {}

    def upsert_entity(self, entity: Entity, mention: Mention) -> None:
        current = self._entities.get(entity.id)
        if current is None:
            self._entities[entity.id] = replace(entity, aliases=merge_aliases(entity.name, [], entity.aliases), degree=0)
        else:
            current.aliases = merge_aliases(current.name, current.aliases, entity.aliases)
            if current.type == "OTHER":
                current.type = entity.type
            if not current.description:
                current.description = entity.description
        mentions = self._mentions.setdefault(entity.id, [])
        if mention not in mentions:
            mentions.append(mention)

    def upsert_relation(self, source_id, target_id, type, mention, evidence, confidence) -> None:
        if source_id not in self._entities or target_id not in self._entities:
            return
        key = f"{source_id}|{type}|{target_id}"
        rel = self._relations.get(key)
        if rel is None:
            rel = self._relations[key] = Relation(source_id, target_id, type, [], [], [], confidence)
        if mention.chunk_id in rel.chunk_ids:
            return
        rel.chunk_ids.append(mention.chunk_id)
        rel.document_ids.append(mention.document_id)
        rel.evidence.append(evidence)
        rel.confidence = max(rel.confidence, confidence)

    def get_entity(self, id: str) -> Entity | None:
        e = self._entities.get(id)
        return replace(e, aliases=list(e.aliases)) if e else None

    def get_entities(self, ids: list[str]) -> list[Entity]:
        return [self.get_entity(i) for i in ids if i in self._entities]

    def find_entities(self, q: str | None, type: str | None, limit: int) -> list[Entity]:
        needle = normalize_name(q) if q else None
        hits = []
        for e in self._entities.values():
            if type and e.type != type:
                continue
            if needle and not any(needle in normalize_name(f) for f in [e.name, *e.aliases]):
                continue
            hits.append(e)
        hits.sort(key=lambda e: (-e.degree, e.name.lower()))
        return [self.get_entity(e.id) for e in hits[:limit]]

    def entity_index(self) -> list[tuple[str, list[str]]]:
        return [(e.id, [e.name, *e.aliases]) for e in self._entities.values()]

    def neighbors(self, ids: list[str]) -> list[Relation]:
        wanted = set(ids)
        return [self._copy(r) for r in self._relations.values() if r.source in wanted or r.target in wanted]

    def mentions(self, ids: list[str]) -> dict[str, list[Mention]]:
        return {i: list(self._mentions.get(i, [])) for i in ids if i in self._entities}

    def remove_document(self, document_id: str) -> list[str]:
        for key, rel in list(self._relations.items()):
            keep = [i for i, d in enumerate(rel.document_ids) if d != document_id]
            rel.chunk_ids = [rel.chunk_ids[i] for i in keep]
            rel.document_ids = [rel.document_ids[i] for i in keep]
            rel.evidence = [rel.evidence[i] for i in keep]
            if not keep:
                del self._relations[key]
        removed = []
        for id, mentions in list(self._mentions.items()):
            mentions[:] = [m for m in mentions if m.document_id != document_id]
            if not mentions:
                removed.append(id)
                del self._mentions[id]
                del self._entities[id]
        for key, rel in list(self._relations.items()):
            if rel.source in removed or rel.target in removed:
                del self._relations[key]
        return removed

    def recompute_degrees(self) -> None:
        counts = Counter()
        for rel in self._relations.values():
            counts[rel.source] += 1
            counts[rel.target] += 1
        for e in self._entities.values():
            e.degree = counts[e.id]

    def stats(self) -> dict:
        return {
            "entities": len(self._entities),
            "relations": len(self._relations),
            "by_type": dict(Counter(e.type for e in self._entities.values())),
            "relation_types": dict(Counter(r.type for r in self._relations.values())),
        }

    def subgraph(self, limit: int) -> tuple[list[Entity], list[Relation]]:
        entities = self.find_entities(None, None, limit)
        ids = {e.id for e in entities}
        rels = [self._copy(r) for r in self._relations.values() if r.source in ids and r.target in ids]
        return entities, rels

    @staticmethod
    def _copy(r: Relation) -> Relation:
        return replace(r, chunk_ids=list(r.chunk_ids), document_ids=list(r.document_ids), evidence=list(r.evidence))
