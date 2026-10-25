"""Neo4j graph store. All queries are parameterized; relationship semantics are a
`type` property on a single `RELATES` label because labels cannot be parameters."""

import logging

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.extraction.normalize import normalize_name
from app.graph.store import Entity, GraphUnavailable, Mention, Relation

log = logging.getLogger(__name__)

_REL_FIELDS = "a.id AS source, b.id AS target, r.type AS type, r.chunk_ids AS chunk_ids, " \
              "r.document_ids AS document_ids, r.evidence AS evidence, r.confidence AS confidence"

_UPSERT_ENTITY = """
MERGE (e:Entity {id: $id})
ON CREATE SET e.name = $name, e.type = $type, e.aliases = [], e.description = $description,
              e.norm = $norm, e.degree = 0
SET e.aliases = reduce(acc = [], a IN coalesce(e.aliases, []) + $aliases |
                       CASE WHEN a = e.name OR a IN acc THEN acc ELSE acc + a END),
    e.type = CASE WHEN e.type = 'OTHER' THEN $type ELSE e.type END,
    e.description = CASE WHEN coalesce(e.description, '') = '' THEN $description ELSE e.description END
SET e.search = [x IN [e.name] + e.aliases | toLower(x)]
MERGE (c:Chunk {id: $chunk_id})
ON CREATE SET c.document_id = $document_id, c.filename = $filename, c.page = $page
MERGE (e)-[:MENTIONED_IN]->(c)
"""

_UPSERT_RELATION = """
MATCH (a:Entity {id: $source}), (b:Entity {id: $target})
MERGE (a)-[r:RELATES {type: $type}]->(b)
ON CREATE SET r.chunk_ids = [], r.document_ids = [], r.evidence = [], r.confidence = $confidence
WITH r WHERE NOT $chunk_id IN r.chunk_ids
SET r.chunk_ids = r.chunk_ids + $chunk_id,
    r.document_ids = r.document_ids + $document_id,
    r.evidence = r.evidence + $evidence,
    r.confidence = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END
"""

_STRIP_PROVENANCE = """
MATCH ()-[r:RELATES]->() WHERE $document_id IN r.document_ids
WITH r, [i IN range(0, size(r.document_ids) - 1) WHERE r.document_ids[i] <> $document_id] AS keep
SET r.chunk_ids = [i IN keep | r.chunk_ids[i]],
    r.document_ids = [i IN keep | r.document_ids[i]],
    r.evidence = [i IN keep | r.evidence[i]]
WITH r WHERE size(r.chunk_ids) = 0
DELETE r
"""

_DELETE_CHUNKS = "MATCH (c:Chunk {document_id: $document_id}) DETACH DELETE c"

_DELETE_ORPHANS = """
MATCH (e:Entity) WHERE NOT EXISTS { (e)-[:MENTIONED_IN]->(:Chunk) }
WITH e, e.id AS id
DETACH DELETE e
RETURN id
"""


def _entity(node) -> Entity:
    return Entity(
        id=node["id"],
        name=node["name"],
        type=node["type"],
        aliases=list(node.get("aliases") or []),
        description=node.get("description") or "",
        degree=node.get("degree") or 0,
    )


def _relation(record) -> Relation:
    return Relation(
        source=record["source"],
        target=record["target"],
        type=record["type"],
        chunk_ids=list(record["chunk_ids"]),
        document_ids=list(record["document_ids"]),
        evidence=list(record["evidence"]),
        confidence=float(record["confidence"]),
    )


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str):
        try:
            self._driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5)
            self._driver.verify_connectivity()
            self._write("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            self._write("CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE")
            self._write("CREATE INDEX chunk_document IF NOT EXISTS FOR (c:Chunk) ON (c.document_id)")
        except (ServiceUnavailable, AuthError, SessionExpired, OSError) as exc:
            raise GraphUnavailable(f"cannot connect to Neo4j at {uri}: {exc}") from exc

    def close(self) -> None:
        self._driver.close()

    def _run(self, query: str, write: bool, **params) -> list:
        try:
            records, _, _ = self._driver.execute_query(
                query, parameters_=params, routing_="w" if write else "r"
            )
            return records
        except (ServiceUnavailable, SessionExpired) as exc:
            raise GraphUnavailable(f"Neo4j unavailable: {exc}") from exc

    def _write(self, query: str, **params) -> list:
        return self._run(query, True, **params)

    def _read(self, query: str, **params) -> list:
        return self._run(query, False, **params)

    def clear(self) -> None:
        self._write("MATCH (n) WHERE n:Entity OR n:Chunk DETACH DELETE n")

    def upsert_entity(self, entity: Entity, mention: Mention) -> None:
        self._write(
            _UPSERT_ENTITY,
            id=entity.id,
            name=entity.name,
            type=entity.type,
            aliases=list(entity.aliases),
            description=entity.description,
            norm=normalize_name(entity.name),
            chunk_id=mention.chunk_id,
            document_id=mention.document_id,
            filename=mention.filename,
            page=mention.page,
        )

    def upsert_relation(self, source_id, target_id, type, mention, evidence, confidence) -> None:
        self._write(
            _UPSERT_RELATION,
            source=source_id,
            target=target_id,
            type=type,
            chunk_id=mention.chunk_id,
            document_id=mention.document_id,
            evidence=evidence,
            confidence=float(confidence),
        )

    def get_entity(self, id: str) -> Entity | None:
        records = self._read("MATCH (e:Entity {id: $id}) RETURN e", id=id)
        return _entity(records[0]["e"]) if records else None

    def get_entities(self, ids: list[str]) -> list[Entity]:
        records = self._read("MATCH (e:Entity) WHERE e.id IN $ids RETURN e", ids=list(ids))
        found = {r["e"]["id"]: _entity(r["e"]) for r in records}
        return [found[i] for i in ids if i in found]

    def find_entities(self, q: str | None, type: str | None, limit: int) -> list[Entity]:
        records = self._read(
            """
            MATCH (e:Entity)
            WHERE ($type IS NULL OR e.type = $type)
              AND ($q IS NULL OR any(s IN e.search WHERE s CONTAINS $q) OR e.norm CONTAINS $norm)
            RETURN e ORDER BY e.degree DESC, toLower(e.name) LIMIT $limit
            """,
            q=q.lower() if q else None,
            norm=normalize_name(q) if q else None,
            type=type,
            limit=int(limit),
        )
        return [_entity(r["e"]) for r in records]

    def entity_index(self) -> list[tuple[str, list[str]]]:
        records = self._read("MATCH (e:Entity) RETURN e.id AS id, [e.name] + e.aliases AS names")
        return [(r["id"], list(r["names"])) for r in records]

    def neighbors(self, ids: list[str]) -> list[Relation]:
        records = self._read(
            f"MATCH (a:Entity)-[r:RELATES]->(b:Entity) WHERE a.id IN $ids OR b.id IN $ids RETURN {_REL_FIELDS}",
            ids=list(ids),
        )
        return [_relation(r) for r in records]

    def mentions(self, ids: list[str]) -> dict[str, list[Mention]]:
        records = self._read(
            """
            MATCH (e:Entity) WHERE e.id IN $ids
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(c:Chunk)
            RETURN e.id AS id, collect(c {.id, .document_id, .filename, .page}) AS chunks
            """,
            ids=list(ids),
        )
        return {
            r["id"]: [Mention(c["id"], c["document_id"], c["filename"], c["page"]) for c in r["chunks"]]
            for r in records
        }

    def remove_document(self, document_id: str) -> list[str]:
        def work(tx):
            tx.run(_STRIP_PROVENANCE, document_id=document_id).consume()
            tx.run(_DELETE_CHUNKS, document_id=document_id).consume()
            return [r["id"] for r in tx.run(_DELETE_ORPHANS)]

        try:
            with self._driver.session() as session:
                return session.execute_write(work)
        except (ServiceUnavailable, SessionExpired) as exc:
            raise GraphUnavailable(f"Neo4j unavailable: {exc}") from exc

    def recompute_degrees(self) -> None:
        self._write("MATCH (e:Entity) SET e.degree = COUNT { (e)-[:RELATES]-() }")

    def stats(self) -> dict:
        entities = self._read("MATCH (e:Entity) RETURN e.type AS type, count(*) AS n")
        relations = self._read("MATCH ()-[r:RELATES]->() RETURN r.type AS type, count(*) AS n")
        return {
            "entities": sum(r["n"] for r in entities),
            "relations": sum(r["n"] for r in relations),
            "by_type": {r["type"]: r["n"] for r in entities},
            "relation_types": {r["type"]: r["n"] for r in relations},
        }

    def subgraph(self, limit: int) -> tuple[list[Entity], list[Relation]]:
        entities = self.find_entities(None, None, limit)
        ids = [e.id for e in entities]
        records = self._read(
            f"MATCH (a:Entity)-[r:RELATES]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids RETURN {_REL_FIELDS}",
            ids=ids,
        )
        return entities, [_relation(r) for r in records]
