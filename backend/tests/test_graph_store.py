import os

import pytest

from app.graph.memory_store import InMemoryGraphStore
from app.graph.store import Entity, Mention

BACKENDS = ["memory"] + (["neo4j"] if os.environ.get("NEO4J_TEST_URI") else [])


@pytest.fixture(params=BACKENDS)
def graph(request):
    if request.param == "memory":
        yield InMemoryGraphStore()
        return
    from app.graph.neo4j_store import Neo4jGraphStore

    store = Neo4jGraphStore(
        os.environ["NEO4J_TEST_URI"],
        os.environ.get("NEO4J_TEST_USER", "neo4j"),
        os.environ.get("NEO4J_TEST_PASSWORD", "loom-password"),
    )
    store.clear()
    yield store
    store.clear()
    store.close()


M_A = Mention("docA:0", "docA", "a.md", None)
M_B = Mention("docB:0", "docB", "b.md", 2)


def add_pair(graph, mention):
    graph.upsert_entity(Entity("alice", "Alice", "PERSON", [], "engineer"), mention)
    graph.upsert_entity(Entity("acme", "Acme", "ORGANIZATION", ["Acme Corp"], ""), mention)
    graph.upsert_relation("alice", "acme", "WORKS_AT", mention, "Alice works at Acme", 0.8)


def test_same_relation_same_chunk_is_one_edge_one_provenance(graph):
    add_pair(graph, M_A)
    add_pair(graph, M_A)
    rels = graph.neighbors(["alice"])
    assert len(rels) == 1
    assert rels[0].chunk_ids == ["docA:0"]
    assert rels[0].document_ids == ["docA"]
    assert rels[0].evidence == ["Alice works at Acme"]


def test_relation_from_second_document_appends_provenance(graph):
    add_pair(graph, M_A)
    add_pair(graph, M_B)
    rels = graph.neighbors(["alice"])
    assert len(rels) == 1
    assert sorted(rels[0].document_ids) == ["docA", "docB"]
    assert sorted(m.chunk_id for m in graph.mentions(["alice"])["alice"]) == ["docA:0", "docB:0"]


def test_entity_merge_unions_aliases_and_fills_type(graph):
    graph.upsert_entity(Entity("acme", "Acme", "OTHER", ["Acme Corp"], ""), M_A)
    graph.upsert_entity(Entity("acme", "Acme", "ORGANIZATION", ["Acme Inc", "Acme Corp"], "a company"), M_B)
    e = graph.get_entity("acme")
    assert e.type == "ORGANIZATION"
    assert sorted(e.aliases) == ["Acme Corp", "Acme Inc"]
    assert e.description == "a company"


def test_remove_document_drops_orphans_only(graph):
    add_pair(graph, M_A)
    add_pair(graph, M_B)
    graph.upsert_entity(Entity("bob", "Bob", "PERSON", [], ""), M_A)
    removed = graph.remove_document("docA")
    assert removed == ["bob"]
    rels = graph.neighbors(["alice"])
    assert rels[0].document_ids == ["docB"]
    assert rels[0].chunk_ids == ["docB:0"]
    removed = graph.remove_document("docB")
    assert sorted(removed) == ["acme", "alice"]
    assert graph.neighbors(["alice"]) == []
    assert graph.stats()["entities"] == 0


def test_neighbors_returns_both_directions(graph):
    add_pair(graph, M_A)
    assert len(graph.neighbors(["acme"])) == 1
    assert graph.neighbors(["acme"])[0].source == "alice"


def test_degrees_stats_find_and_subgraph(graph):
    add_pair(graph, M_A)
    graph.upsert_entity(Entity("falcon", "Falcon", "PROJECT", [], ""), M_A)
    graph.upsert_relation("alice", "falcon", "LEADS", M_A, "Alice works at Acme", 0.5)
    graph.recompute_degrees()
    assert graph.get_entity("alice").degree == 2
    stats = graph.stats()
    assert stats["entities"] == 3
    assert stats["relations"] == 2
    assert stats["by_type"]["PERSON"] == 1
    assert [e.id for e in graph.find_entities("acme corp", None, 10)] == ["acme"]
    assert [e.id for e in graph.find_entities(None, "PROJECT", 10)] == ["falcon"]
    assert graph.find_entities(None, None, 1)[0].id == "alice"
    entities, relations = graph.subgraph(limit=2)
    assert len(entities) == 2
    assert "alice" in {e.id for e in entities}
    assert all(r.source in {e.id for e in entities} and r.target in {e.id for e in entities} for r in relations)


def test_entity_index_and_get_entities(graph):
    add_pair(graph, M_A)
    index = dict(graph.entity_index())
    assert sorted(index["acme"]) == ["Acme", "Acme Corp"]
    assert [e.id for e in graph.get_entities(["acme", "missing", "alice"])] == ["acme", "alice"]
    assert graph.get_entity("missing") is None
