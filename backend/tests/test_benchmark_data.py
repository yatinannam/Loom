import json

from app.config import REPO_ROOT

BENCH = REPO_ROOT / "data" / "benchmark"
CATEGORIES = {"direct", "relationship", "two_hop", "three_hop", "multi_document", "insufficient_evidence",
              "retrieval_trap"}


def load():
    return json.loads((BENCH / "questions.json").read_text(encoding="utf-8"))


def test_question_set_shape():
    questions = load()
    assert len(questions) >= 20
    assert len({q["id"] for q in questions}) == len(questions)
    counts = {c: sum(q["category"] == c for q in questions) for c in CATEGORIES}
    assert set(q["category"] for q in questions) == CATEGORIES
    assert all(counts[c] >= 3 for c in ("two_hop", "three_hop", "multi_document"))
    assert counts["insufficient_evidence"] >= 2


def test_required_documents_exist_and_keywords_are_in_them():
    for q in load():
        if q["category"] == "insufficient_evidence":
            assert q["answer_keywords"] == [] and q["required_documents"] == []
            continue
        texts = []
        for name in q["required_documents"]:
            path = BENCH / name
            assert path.exists(), f"{q['id']}: missing {name}"
            texts.append(path.read_text(encoding="utf-8").lower())
        corpus = "\n".join(texts)
        for group in q["answer_keywords"]:
            assert any(alt.lower() in corpus for alt in group), f"{q['id']}: {group} not in required documents"


def test_benchmark_contains_demo_corpus():
    for name in ("employee.md", "project.md", "technology.md"):
        assert (BENCH / name).read_bytes() == (REPO_ROOT / "data" / "demo" / name).read_bytes()
