from app.llm.provider import LLMRateLimited
from tests.conftest import DEMO_DIR, make_env
from tests.fixtures.demo_llm import demo_fake_llm

EXPECTED = {
    ("alice", "WORKS_AT", "acme-technologies"): "employee.md",
    ("alice", "LEADS", "autonomous-systems"): "employee.md",
    ("autonomous-systems", "DEVELOPED", "project-falcon"): "project.md",
    ("project-falcon", "USES", "edgecore"): "project.md",
    ("edgecore", "DEPLOYED_ON", "nvidia-jetson"): "technology.md",
}


def all_relations(graph):
    ids = [e for e, _ in graph.entity_index()]
    return {(r.source, r.type, r.target): r for r in graph.neighbors(ids)}


def test_demo_graph_has_expected_relations_with_provenance(demo_env):
    rels = all_relations(demo_env.graph)
    for key, filename in EXPECTED.items():
        assert key in rels, key
        assert rels[key].document_ids == [demo_env.doc_ids[filename]]
        assert rels[key].evidence and rels[key].chunk_ids


def test_team_name_variants_merge_into_one_entity(demo_env):
    team = demo_env.graph.get_entity("autonomous-systems")
    assert "Autonomous Systems team" in team.aliases
    assert demo_env.graph.get_entity("autonomous-systems-team") is None


def test_status_and_counts_recorded(demo_env):
    doc = demo_env.registry.get_document(demo_env.doc_ids["employee.md"])
    assert doc.status == "ingested"
    assert doc.chunk_count == 1
    assert doc.entity_count == 3
    assert doc.relation_count == 2
    assert doc.error is None


def test_reingest_is_idempotent(demo_env):
    before = (demo_env.graph.stats(), demo_env.vector.count_chunks())
    demo_env.ingestion.ingest(demo_env.doc_ids["project.md"])
    after = (demo_env.graph.stats(), demo_env.vector.count_chunks())
    assert before == after


def test_same_file_uploaded_twice_has_same_id(demo_env):
    path = DEMO_DIR / "employee.md"
    row = demo_env.ingestion.add_file(path.name, path.read_bytes())
    assert row.id == demo_env.doc_ids["employee.md"]
    assert len(demo_env.registry.list_documents()) == 3


def test_remove_deletes_only_that_document(demo_env):
    tech = demo_env.doc_ids["technology.md"]
    demo_env.ingestion.remove(tech)
    assert demo_env.registry.get_document(tech) is None
    assert demo_env.vector.chunks_for_document(tech) == []
    assert demo_env.graph.get_entity("nvidia-jetson") is None
    assert demo_env.graph.get_entity("edgecore") is not None  # still mentioned in project.md
    rels = all_relations(demo_env.graph)
    assert ("project-falcon", "USES", "edgecore") in rels
    assert ("edgecore", "DEPLOYED_ON", "nvidia-jetson") not in rels
    assert demo_env.vector.search_entities("NVIDIA Jetson", k=5)[0][0] != "nvidia-jetson"


def test_rate_limit_mid_ingestion_fails_cleanly(tmp_path):
    first = "Alice works at Acme Technologies and leads the Autonomous Systems team."
    second = "Zed runs the Orbit lab in Lisbon."
    llm = demo_fake_llm(extra=[(second, LLMRateLimited("daily token limit reached"))])
    env = make_env(tmp_path, llm=llm, chunk_size=80, chunk_overlap=10)
    row = env.ingestion.add_file("two.md", f"{first}\n\n{second}\n".encode())
    env.ingestion.ingest(row.id)
    doc = env.registry.get_document(row.id)
    assert doc.status == "failed"
    assert "daily token limit reached" in doc.error
    assert env.vector.chunks_for_document(row.id) == []
    assert env.graph.stats()["entities"] == 0


def test_unsupported_evidence_logged_as_extraction_error(tmp_path):
    import json

    text = "Bob works at Initech."
    bogus = json.dumps({
        "entities": [{"name": "Bob", "type": "PERSON"}, {"name": "Initech", "type": "ORGANIZATION"}],
        "relations": [{"source": "Bob", "target": "Initech", "type": "FOUNDED", "evidence": "Bob founded Initech in 1999"}],
    })
    env = make_env(tmp_path, llm=demo_fake_llm(extra=[(text, bogus)]))
    row = env.ingestion.add_file("bob.txt", text.encode())
    env.ingestion.ingest(row.id)
    assert env.registry.get_document(row.id).status == "ingested"
    errors = env.registry.list_extraction_errors(row.id)
    assert any("evidence" in e["message"] for e in errors)
    assert env.graph.stats()["relations"] == 0


def test_file_without_text_fails_with_reason(tmp_path):
    from tests.pdf_fixture import make_pdf

    env = make_env(tmp_path)
    row = env.ingestion.add_file("scan.pdf", make_pdf([""]))
    env.ingestion.ingest(row.id)
    doc = env.registry.get_document(row.id)
    assert doc.status == "failed"
    assert "no extractable text" in doc.error
