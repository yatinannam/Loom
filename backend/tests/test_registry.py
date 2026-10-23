from app.registry import Registry


def make(tmp_path):
    return Registry(tmp_path / "loom.db")


def test_upsert_document_twice_keeps_one_row(tmp_path):
    reg = make(tmp_path)
    reg.upsert_document("d1", "a.md", "text/markdown", 10)
    reg.set_status("d1", "ingested", chunk_count=3)
    reg.upsert_document("d1", "a.md", "text/markdown", 10)
    docs = reg.list_documents()
    assert len(docs) == 1
    assert docs[0].status == "ingested"
    assert docs[0].chunk_count == 3


def test_set_status_records_error_and_counts(tmp_path):
    reg = make(tmp_path)
    reg.upsert_document("d1", "a.md", "text/markdown", 10)
    reg.set_status("d1", "failed", error="boom", entity_count=2, relation_count=1, pages=None)
    doc = reg.get_document("d1")
    assert doc.status == "failed"
    assert doc.error == "boom"
    assert doc.entity_count == 2
    assert doc.relation_count == 1
    reg.set_status("d1", "processing")
    assert reg.get_document("d1").error is None


def test_get_missing_document_returns_none(tmp_path):
    assert make(tmp_path).get_document("nope") is None


def test_delete_document_removes_row_and_errors(tmp_path):
    reg = make(tmp_path)
    reg.upsert_document("d1", "a.md", "text/markdown", 10)
    reg.add_extraction_error("d1", "d1:0", "bad json", "{")
    reg.delete_document("d1")
    assert reg.get_document("d1") is None
    assert reg.list_extraction_errors("d1") == []


def test_extraction_errors_round_trip_and_clear(tmp_path):
    reg = make(tmp_path)
    reg.upsert_document("d1", "a.md", "text/markdown", 10)
    reg.add_extraction_error("d1", "d1:0", "bad json", "{")
    errors = reg.list_extraction_errors("d1")
    assert errors[0]["chunk_id"] == "d1:0"
    assert errors[0]["message"] == "bad json"
    assert errors[0]["raw_response"] == "{"
    reg.clear_extraction_errors("d1")
    assert reg.list_extraction_errors("d1") == []


def test_activity_newest_first(tmp_path):
    reg = make(tmp_path)
    reg.log_activity("ingest", "first")
    reg.log_activity("query", "second")
    items = reg.recent_activity(limit=1)
    assert len(items) == 1
    assert items[0]["message"] == "second"
    assert items[0]["kind"] == "query"


def test_eval_run_lifecycle(tmp_path):
    reg = make(tmp_path)
    run_id = reg.create_eval_run({"modes": ["standard"]})
    reg.add_eval_result(run_id, "q1", "standard", {"correct": True})
    reg.finish_eval_run(run_id, "completed", {"standard": {"accuracy": 1.0}})
    run = reg.get_eval_run(run_id)
    assert run["status"] == "completed"
    assert run["config"] == {"modes": ["standard"]}
    assert run["summary"] == {"standard": {"accuracy": 1.0}}
    assert reg.latest_eval_run()["id"] == run_id
    assert [r["id"] for r in reg.list_eval_runs()] == [run_id]
    assert reg.eval_results(run_id) == [
        {"question_id": "q1", "mode": "standard", "record": {"correct": True}}
    ]
