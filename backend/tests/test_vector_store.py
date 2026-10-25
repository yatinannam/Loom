import uuid

import chromadb
import pytest

from app.models import ChunkRecord
from app.vector.store import ChromaVectorStore
from tests.fakes import HashEmbedder


def chunk(doc, i, text):
    return ChunkRecord(id=f"{doc}:{i}", document_id=doc, filename=f"{doc}.md", page=None,
                       chunk_index=i, text=text, char_start=0, char_end=len(text))


@pytest.fixture
def store():
    return ChromaVectorStore(chromadb.EphemeralClient(), HashEmbedder(), collection_prefix=uuid.uuid4().hex[:8])


def test_upsert_twice_keeps_count(store):
    chunks = [chunk("a", 0, "alice leads the team"), chunk("a", 1, "falcon uses edgecore")]
    store.upsert_chunks(chunks)
    store.upsert_chunks(chunks)
    assert store.count_chunks() == 2


def test_search_ranks_shared_words_first(store):
    store.upsert_chunks([chunk("a", 0, "alice leads the autonomous systems team"),
                         chunk("b", 0, "edgecore is deployed on jetson devices")])
    results = store.search("which devices run edgecore", k=2, min_score=0.0)
    assert results[0].chunk.id == "b:0"
    assert results[0].score > results[1].score
    assert results[0].chunk.filename == "b.md"


def test_min_score_filters(store):
    store.upsert_chunks([chunk("a", 0, "alice leads the team"), chunk("b", 0, "zebra quantum pancake")])
    results = store.search("alice leads", k=5, min_score=0.3)
    assert [r.chunk.id for r in results] == ["a:0"]


def test_delete_document_only_removes_that_document(store):
    store.upsert_chunks([chunk("a", 0, "one"), chunk("a", 1, "two"), chunk("b", 0, "three")])
    store.delete_document("a")
    assert store.count_chunks() == 1
    assert store.chunks_for_document("a") == []
    assert [c.id for c in store.chunks_for_document("b")] == ["b:0"]


def test_get_chunks_keeps_order_and_skips_missing(store):
    store.upsert_chunks([chunk("a", 0, "one"), chunk("a", 1, "two")])
    assert [c.id for c in store.get_chunks(["a:1", "zz:9", "a:0"])] == ["a:1", "a:0"]


def test_chunks_for_document_sorted_by_index(store):
    store.upsert_chunks([chunk("a", 2, "c"), chunk("a", 0, "a"), chunk("a", 1, "b")])
    assert [c.chunk_index for c in store.chunks_for_document("a")] == [0, 1, 2]


def test_entity_search_returns_matching_id(store):
    store.upsert_entities([("edgecore", "EdgeCore: edge computing platform", "TECHNOLOGY"),
                           ("alice", "Alice: team lead", "PERSON")])
    hits = store.search_entities("edgecore platform", k=1)
    assert hits[0][0] == "edgecore"
    store.delete_entities(["edgecore"])
    assert store.search_entities("edgecore platform", k=1)[0][0] == "alice"


def test_empty_store_search_returns_empty(store):
    assert store.search("anything", k=3, min_score=0.0) == []
    assert store.search_entities("anything", k=3) == []
