import ast
import inspect

import app.retrieval.standard as standard_module
from app.models import ChunkRecord
from app.retrieval.fusion import rrf_fuse
from app.retrieval.graph import retrieve_graph
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.standard import retrieve_standard
from app.retrieval.types import GraphPath, PathStep, RetrievedChunk
from tests.fixtures.demo_llm import ALICE_QUESTION


def rc(id, source, rank):
    chunk = ChunkRecord(id=id, document_id=id.split(":")[0], filename="f", page=None, chunk_index=0,
                        text=id, char_start=0, char_end=1)
    return RetrievedChunk(chunk=chunk, score=1.0 / rank, sources={source: {"rank": rank, "score": 1.0 / rank}})


def test_rrf_deduplicates_and_merges_sources():
    fused = rrf_fuse({"vector": [rc("a:0", "vector", 1), rc("b:0", "vector", 2)],
                      "graph": [rc("b:0", "graph", 1), rc("c:0", "graph", 2)]},
                     weights={"vector": 1.0, "graph": 1.0}, k=60, limit=10)
    ids = [c.chunk.id for c in fused]
    assert ids[0] == "b:0"
    assert sorted(ids) == ["a:0", "b:0", "c:0"]
    assert set(fused[0].sources) == {"vector", "graph"}
    assert abs(fused[0].score - (1 / 62 + 1 / 61)) < 1e-12


def test_rrf_weights_and_budget():
    fused = rrf_fuse({"vector": [rc("a:0", "vector", 1)], "graph": [rc("c:0", "graph", 1)]},
                     weights={"vector": 1.0, "graph": 2.0}, k=60, limit=1)
    assert [c.chunk.id for c in fused] == ["c:0"]


def test_standard_retrieval_has_no_graph_dependency():
    tree = ast.parse(inspect.getsource(standard_module))
    imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in imported if m and m.startswith("app.graph")]


def test_standard_retrieval_ranks_by_similarity(demo_env):
    res = retrieve_standard(demo_env.vector, "Where is EdgeCore deployed?", demo_env.settings)
    assert res.mode == "standard"
    assert res.chunks[0].chunk.filename == "technology.md"
    assert res.chunks[0].sources["vector"]["rank"] == 1
    assert res.paths == []


def deps(env):
    return dict(llm=env.llm, vector=env.vector, graph=env.graph, resolver=env.resolver, settings=env.settings)


def test_graph_retrieval_reaches_all_three_demo_documents(demo_env):
    res = retrieve_graph(ALICE_QUESTION, **deps(demo_env))
    assert {c.chunk.filename for c in res.chunks} == {"employee.md", "project.md", "technology.md"}
    assert "alice" in {s.entity_id for s in res.seeds}
    rendered = [p.render() for p in res.paths]
    assert any("Alice -[LEADS]-> Autonomous Systems -[DEVELOPED]-> Project Falcon -[USES]-> EdgeCore" == r
               for r in rendered), rendered
    assert all(c.sources["graph"]["rank"] == i + 1 for i, c in enumerate(res.chunks))
    assert res.usage


def test_unknown_entity_gives_empty_graph_and_vector_only_hybrid(demo_env):
    q = "What is the capital of Zorblax?"
    g = retrieve_graph(q, **deps(demo_env))
    assert g.chunks == [] and g.paths == []
    assert "no query entity" in g.route_reason
    h = retrieve_hybrid(q, **deps(demo_env))
    assert h.route == "vector_only"
    standard = retrieve_standard(demo_env.vector, q, demo_env.settings)
    assert [c.chunk.id for c in h.chunks] == [c.chunk.id for c in standard.chunks]


def test_hybrid_fuses_and_respects_budget(demo_env):
    demo_env.settings.max_evidence_chunks = 2
    h = retrieve_hybrid(ALICE_QUESTION, **deps(demo_env))
    assert h.route == "hybrid"
    assert len(h.chunks) == 2
    assert len({c.chunk.id for c in h.chunks}) == 2
    assert h.paths


def test_path_render_backward():
    p = GraphPath(steps=[PathStep("a", "A", "LEADS", "b", "B", True), PathStep("c", "C", "USES", "b", "B", False)],
                  score=1.0, chunk_ids=[])
    assert p.render() == "A -[LEADS]-> B <-[USES]- C"
