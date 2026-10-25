import pytest
from fastapi.testclient import TestClient

from app.graph.lazy import LazyGraph
from app.graph.store import GraphUnavailable
from app.llm.provider import OpenAICompatibleLLM
from app.main import create_app
from app.services import Services
from tests.conftest import DEMO_DIR, make_env
from tests.fixtures.demo_llm import ALICE_QUESTION


def services_from(env, graph=None, llm=None) -> Services:
    graph = graph or LazyGraph(lambda: env.graph)
    llm = llm or env.llm
    env.ingestion.graph = graph
    env.ingestion.llm = llm
    env.resolver.graph = graph
    return Services.assemble(env.settings, env.registry, env.vector, graph, llm, env.resolver, env.ingestion)


@pytest.fixture
def client(tmp_path):
    env = make_env(tmp_path)
    with TestClient(create_app(services_from(env))) as c:
        yield c


def down_graph():
    def factory():
        raise GraphUnavailable("cannot connect to Neo4j at bolt://nowhere")
    return LazyGraph(factory)


def upload(client, *names):
    files = [("files", (n, (DEMO_DIR / n).read_bytes(), "text/markdown")) for n in names]
    return client.post("/api/documents/upload", files=files)


def test_upload_ingests_and_lists(client):
    resp = upload(client, "employee.md", "project.md", "technology.md")
    assert resp.status_code == 201
    ids = [d["id"] for d in resp.json()]
    docs = {d["id"]: d for d in client.get("/api/documents").json()}
    assert all(docs[i]["status"] == "ingested" for i in ids)
    assert client.get(f"/api/documents/{ids[0]}").json()["filename"] == "employee.md"
    chunks = client.get(f"/api/documents/{ids[0]}/chunks").json()
    assert chunks[0]["text"].startswith("# Employee")
    assert client.get(f"/api/documents/{ids[0]}/errors").json() == []
    stats = client.get("/api/stats").json()
    assert stats["documents"] == 3 and stats["chunks"] == 3 and stats["entities"] >= 6


def test_upload_unsupported_type(client):
    resp = client.post("/api/documents/upload", files=[("files", ("tool.exe", b"MZ", "application/octet-stream"))])
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_type"


def test_unknown_document_404(client):
    resp = client.get("/api/documents/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_delete_document(client):
    doc_id = upload(client, "employee.md").json()[0]["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_reingest_returns_202(client):
    doc_id = upload(client, "employee.md").json()[0]["id"]
    resp = client.post(f"/api/documents/{doc_id}/ingest")
    assert resp.status_code == 202
    assert client.get(f"/api/documents/{doc_id}").json()["status"] == "ingested"


def test_query_invalid_mode_422(client):
    resp = client.post("/api/query", json={"question": "q", "mode": "magic"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_query_returns_answer_paths_and_citations(client):
    upload(client, "employee.md", "project.md", "technology.md")
    body = client.post("/api/query", json={"question": ALICE_QUESTION, "mode": "graph"}).json()
    assert "Jetson" in body["answer"]["answer"]
    assert any(p["rendered"].startswith("Alice -[LEADS]->") for p in body["retrieval"]["paths"])
    assert body["retrieval"]["chunks"][0]["chunk"]["filename"].endswith(".md")
    assert body["answer"]["citations"]


def test_graph_endpoints(client):
    upload(client, "employee.md", "project.md", "technology.md")
    stats = client.get("/api/graph/stats").json()
    assert stats["relations"] >= 5
    hits = client.get("/api/graph/entities", params={"q": "edge"}).json()
    assert hits[0]["id"] == "edgecore"
    detail = client.get("/api/graph/entities/edgecore").json()
    assert {m["filename"] for m in detail["mentions"]} == {"project.md", "technology.md"}
    assert any(r["type"] == "DEPLOYED_ON" for r in detail["relations"])
    hood = client.get("/api/graph/entities/edgecore/neighbors", params={"hops": 2}).json()
    assert "autonomous-systems" in {e["id"] for e in hood["entities"]}
    sub = client.get("/api/graph/subgraph", params={"limit": 50}).json()
    assert len(sub["entities"]) >= 6 and sub["relations"]
    assert client.get("/api/graph/entities/nope").status_code == 404


def test_neo4j_down(tmp_path):
    env = make_env(tmp_path)
    with TestClient(create_app(services_from(env, graph=down_graph()))) as c:
        health = c.get("/api/health").json()
        assert health["neo4j"] == "down"
        resp = c.get("/api/graph/stats")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "graph_unavailable"
        assert upload(c, "employee.md").status_code == 503
        assert c.get("/api/stats").json()["entities"] is None


def test_llm_without_key(tmp_path):
    env = make_env(tmp_path)
    llm = OpenAICompatibleLLM("https://llm.invalid/v1", "", 5, 10, 0, cache=None)
    with TestClient(create_app(services_from(env, llm=llm))) as c:
        assert c.get("/api/health").json()["llm_configured"] is False
        resp = c.post("/api/query", json={"question": "Where is EdgeCore deployed?", "mode": "graph"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "llm_not_configured"
        resp = upload(c, "employee.md")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "llm_not_configured"


def test_activity_feed(client):
    upload(client, "employee.md")
    items = client.get("/api/activity").json()
    assert items[0]["kind"] == "ingest"


def test_evaluation_endpoints(tmp_path):
    import time

    from app.evaluation.runner import EvaluationService
    from tests.test_runner import QUESTIONS, ZORBLAX, INSUFFICIENT
    from tests.fixtures.demo_llm import demo_fake_llm

    env = make_env(tmp_path, llm=demo_fake_llm(extra=[(f"Question: {ZORBLAX}", INSUFFICIENT)]), benchmark_dir=DEMO_DIR)
    svc = services_from(env)
    qpath = tmp_path / "q.json"
    import json
    qpath.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    svc.evaluation = EvaluationService(svc, questions_path=qpath)
    with TestClient(create_app(svc)) as c:
        assert c.get("/api/evaluation/results").status_code == 404
        assert len(c.post("/api/evaluation/load-corpus").json()["document_ids"]) == 3
        assert c.post("/api/evaluation/run", json={"modes": ["magic"]}).status_code == 400
        run = c.post("/api/evaluation/run", json={"modes": ["standard", "graph"]})
        assert run.status_code == 202
        run_id = run.json()["id"]
        for _ in range(100):
            if c.get(f"/api/evaluation/runs/{run_id}").json()["status"] != "running":
                break
            time.sleep(0.05)
        body = c.get(f"/api/evaluation/runs/{run_id}").json()
        assert body["status"] == "completed"
        assert body["progress"]["done"] == 4
        assert len(c.get(f"/api/evaluation/runs/{run_id}/results").json()) == 4
        assert c.get("/api/evaluation/results").json()["run"]["id"] == run_id
        csv_resp = c.get(f"/api/evaluation/runs/{run_id}/export", params={"format": "csv"})
        assert csv_resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in csv_resp.headers["content-disposition"]
        assert [r["id"] for r in c.get("/api/evaluation/runs").json()] == [run_id]


def test_upload_with_one_invalid_file_stores_nothing(client):
    files = [("files", ("employee.md", (DEMO_DIR / "employee.md").read_bytes(), "text/markdown")),
             ("files", ("tool.exe", b"MZ", "application/octet-stream"))]
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 400
    assert client.get("/api/documents").json() == []
