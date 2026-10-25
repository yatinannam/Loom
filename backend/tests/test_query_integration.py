import pytest

from app.query import QueryService
from tests.fixtures.demo_llm import ALICE_QUESTION

DEMO_FILES = {"employee.md", "project.md", "technology.md"}


def service(env):
    return QueryService(llm=env.llm, vector=env.vector, graph=env.graph, resolver=env.resolver,
                        settings=env.settings, registry=env.registry)


@pytest.mark.parametrize("mode", ["standard", "graph", "hybrid"])
def test_alice_question_in_each_mode(demo_env, mode):
    resp = service(demo_env).run(ALICE_QUESTION, mode)
    assert resp.mode == mode
    assert "Jetson" in resp.answer.answer
    assert resp.answer.citations
    for c in resp.answer.citations:
        assert set(c.filenames) <= DEMO_FILES and c.filenames
    assert resp.timings["total_ms"] >= resp.timings["retrieval_ms"]
    assert resp.usage["llm_calls"] >= 1


def test_graph_mode_surfaces_paths_and_all_documents(demo_env):
    resp = service(demo_env).run(ALICE_QUESTION, "graph")
    assert resp.retrieval.paths
    assert {c.chunk.filename for c in resp.retrieval.chunks} == DEMO_FILES


def test_unknown_entity_graph_mode_reports_insufficient(demo_env):
    resp = service(demo_env).run("What is the capital of Zorblax?", "graph")
    assert resp.answer.insufficient_evidence is True
    assert resp.retrieval.chunks == []


def test_overrides_are_validated(demo_env):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        service(demo_env).run(ALICE_QUESTION, "graph", {"max_hops": 9})
    with pytest.raises(ValueError):
        service(demo_env).run(ALICE_QUESTION, "graph", {"llm_api_key": "x"})


def test_query_logged_in_activity(demo_env):
    service(demo_env).run(ALICE_QUESTION, "standard")
    assert demo_env.registry.recent_activity(1)[0]["kind"] == "query"
