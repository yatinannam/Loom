import uuid

import chromadb

from app.graph.memory_store import InMemoryGraphStore
from app.graph.resolution import EntityResolver
from app.graph.store import Entity, Mention
from app.vector.store import ChromaVectorStore
from tests.fakes import HashEmbedder

M = Mention("d:0", "d", "d.md", None)


def setup():
    graph = InMemoryGraphStore()
    vector = ChromaVectorStore(chromadb.EphemeralClient(), HashEmbedder(), uuid.uuid4().hex[:8])
    graph.upsert_entity(Entity("acme-technologies", "Acme Technologies", "ORGANIZATION", ["Acme"], ""), M)
    graph.upsert_entity(Entity("alice", "Alice", "PERSON", [], ""), M)
    graph.upsert_entity(Entity("edgecore", "EdgeCore", "TECHNOLOGY", [], "edge computing platform"), M)
    vector.upsert_entities([("edgecore", "EdgeCore: edge computing platform", "TECHNOLOGY")])
    resolver = EntityResolver(graph, vector)
    resolver.refresh()
    return resolver


def test_alias_match_returns_existing_id():
    assert setup().resolve_ingest("ACME", []) == "acme-technologies"


def test_new_alias_resolves_via_existing_name():
    assert setup().resolve_ingest("Acme Industries", ["Acme Technologies"]) == "acme-technologies"


def test_near_but_distinct_names_do_not_merge():
    assert setup().resolve_ingest("Acme Tech", []) is None


def test_fuzzy_match_merges_tiny_spelling_difference():
    assert setup().resolve_ingest("Acme Technologies Inc", []) is None
    assert setup().resolve_ingest("Acme Technologes", []) == "acme-technologies"


def test_register_makes_new_entity_resolvable():
    resolver = setup()
    resolver.register("project-falcon", ["Project Falcon", "Falcon"])
    assert resolver.resolve_ingest("falcon", []) == "project-falcon"


def test_query_scan_finds_entity_named_in_question():
    seeds = setup().resolve_query([], "Who is Alice's manager?", min_score=0.5, limit=5)
    assert [(s.entity_id, s.method) for s in seeds] == [("alice", "scan")]


def test_query_mention_exact_and_alias():
    seeds = setup().resolve_query(["Alice", "Acme"], "q", min_score=0.5, limit=5)
    assert {(s.entity_id, s.method) for s in seeds} == {("alice", "exact"), ("acme-technologies", "alias")}


def test_query_embedding_fallback():
    seeds = setup().resolve_query(["edge computing platform"], "q", min_score=0.3, limit=5)
    assert [(s.entity_id, s.method) for s in seeds] == [("edgecore", "embedding")]


def test_query_unknown_mention_gives_nothing():
    assert setup().resolve_query(["Zorblax"], "Tell me about Zorblax", min_score=0.5, limit=5) == []


def test_query_limit_and_dedupe():
    seeds = setup().resolve_query(["Alice", "alice"], "Alice and Acme and EdgeCore", min_score=0.5, limit=2)
    assert len(seeds) == 2
    assert len({s.entity_id for s in seeds}) == 2


def test_query_does_not_reset_index_used_by_concurrent_ingestion():
    # Ingestion registers names before they are visible through entity_index();
    # a query running meanwhile must not drop them (that would create duplicate nodes).
    resolver = setup()
    resolver.register("project-falcon", ["Project Falcon", "Falcon"])
    resolver.resolve_query(["Alice"], "Who is Alice?", min_score=0.5, limit=5)
    assert resolver.resolve_ingest("Falcon", []) == "project-falcon"


def test_query_sees_entities_added_to_graph_after_refresh():
    resolver = setup()
    resolver.graph.upsert_entity(Entity("lumen-labs", "Lumen Labs", "ORGANIZATION", [], ""), M)
    seeds = resolver.resolve_query(["Lumen Labs"], "q", min_score=0.5, limit=5)
    assert [s.entity_id for s in seeds] == ["lumen-labs"]
