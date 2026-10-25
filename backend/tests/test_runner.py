import csv
import io
import json

import pytest

from app.evaluation.runner import EvaluationService
from app.graph.lazy import LazyGraph
from app.llm.provider import LLMRateLimited
from app.services import Services
from tests.conftest import DEMO_DIR, make_env
from tests.fixtures.demo_llm import ALICE_QUESTION, demo_fake_llm

ZORBLAX = "What is the capital of Zorblax?"
INSUFFICIENT = json.dumps({"answer": "Not stated.", "explanation": "", "citations": [],
                           "insufficient_evidence": True, "conflicts": []})
QUESTIONS = [
    {"id": "q1", "category": "three_hop", "question": ALICE_QUESTION, "reference_answer": "NVIDIA Jetson via EdgeCore",
     "answer_keywords": [["jetson"], ["edgecore"]],
     "required_documents": ["employee.md", "project.md", "technology.md"]},
    {"id": "q2", "category": "insufficient_evidence", "question": ZORBLAX, "reference_answer": "Not in documents",
     "answer_keywords": [], "required_documents": []},
]


def build(tmp_path, llm=None):
    qpath = tmp_path / "questions.json"
    qpath.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    env = make_env(tmp_path, llm=llm or demo_fake_llm(extra=[(f"Question: {ZORBLAX}", INSUFFICIENT)]),
                   benchmark_dir=DEMO_DIR)
    graph = LazyGraph(lambda: env.graph)
    env.ingestion.graph = env.resolver.graph = graph
    services = Services.assemble(env.settings, env.registry, env.vector, graph, env.llm, env.resolver, env.ingestion)
    return env, EvaluationService(services, questions_path=qpath)


def test_load_corpus_ingests_benchmark_dir(tmp_path):
    env, ev = build(tmp_path)
    ids = ev.load_corpus()
    assert len(ids) == 3
    assert all(env.registry.get_document(i).status == "ingested" for i in ids)


def test_run_records_every_question_and_mode(tmp_path):
    env, ev = build(tmp_path)
    ev.load_corpus()
    run_id = ev.run_now(["standard", "graph", "hybrid"])
    run = env.registry.get_eval_run(run_id)
    assert run["status"] == "completed"
    assert run["config"]["corpus_mismatch"] is False
    results = env.registry.eval_results(run_id)
    assert len(results) == 6
    graph_q1 = next(r["record"] for r in results if r["mode"] == "graph" and r["question_id"] == "q1")
    assert graph_q1["metrics"]["correct"] is True
    assert graph_q1["metrics"]["context_recall"] == 1.0
    assert graph_q1["paths"]
    assert graph_q1["total_ms"] >= graph_q1["retrieval_ms"]
    q2 = [r["record"] for r in results if r["question_id"] == "q2"]
    assert all(r["metrics"]["correct"] for r in q2)
    summary = run["summary"]
    assert set(summary["modes"]) == {"standard", "graph", "hybrid"}
    assert summary["modes"]["graph"]["accuracy"] == 1.0
    assert summary["modes"]["graph"]["questions"] == 2
    assert summary["by_category"]["three_hop"]["graph"] == 1.0
    assert ev.progress(run_id)["done"] == 6


def test_extra_document_flags_corpus_mismatch(tmp_path):
    env, ev = build(tmp_path)
    ev.load_corpus()
    row = env.ingestion.add_file("extra.md", b"Alice works at Acme Technologies and leads the Autonomous Systems team.\nextra")
    env.ingestion.ingest(row.id)
    run_id = ev.run_now(["standard"])
    assert env.registry.get_eval_run(run_id)["config"]["corpus_mismatch"] is True


def test_rate_limit_marks_run_failed(tmp_path):
    llm = demo_fake_llm(extra=[(f"Question: {ALICE_QUESTION}", LLMRateLimited("daily limit"))])
    env, ev = build(tmp_path, llm=llm)
    ev.load_corpus()
    run_id = ev.run_now(["standard"])
    run = env.registry.get_eval_run(run_id)
    assert run["status"] == "failed"
    assert "daily limit" in ev.progress(run_id)["error"]


def test_csv_and_json_export(tmp_path):
    env, ev = build(tmp_path)
    ev.load_corpus()
    run_id = ev.run_now(["standard", "graph"])
    content, media = ev.export(run_id, "csv")
    assert media == "text/csv"
    rows = list(csv.DictReader(io.StringIO(content)))
    assert len(rows) == 4
    assert {"question_id", "mode", "correct", "f1", "context_recall", "total_ms"} <= set(rows[0])
    content, media = ev.export(run_id, "json")
    body = json.loads(content)
    assert body["run"]["id"] == run_id and len(body["results"]) == 4


def test_only_one_run_at_a_time(tmp_path):
    env, ev = build(tmp_path)
    ev._running = "busy"
    with pytest.raises(RuntimeError):
        ev.start(["standard"])


def test_malformed_answer_is_recorded_and_run_continues(tmp_path):
    llm = demo_fake_llm(extra=[(f"Question: {ALICE_QUESTION}", "this is not json"),
                               (f"Question: {ZORBLAX}", INSUFFICIENT)])
    env, ev = build(tmp_path, llm=llm)
    ev.load_corpus()
    run_id = ev.run_now(["standard"])
    run = env.registry.get_eval_run(run_id)
    assert run["status"] == "completed"
    records = {r["question_id"]: r["record"] for r in env.registry.eval_results(run_id)}
    assert records["q1"]["error"].startswith("llm_bad_response")
    assert records["q1"]["metrics"]["correct"] is False
    assert records["q2"]["metrics"]["correct"] is True
    assert run["summary"]["modes"]["standard"]["errors"] == 1
    assert run["summary"]["modes"]["standard"]["accuracy"] == 0.5
