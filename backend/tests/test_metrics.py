from app.evaluation.metrics import (
    citation_scores,
    context_recall,
    keyword_correct,
    normalize_answer,
    question_correct,
    token_f1,
)


def test_normalize_answer():
    assert normalize_answer("The  NVIDIA Jetson, devices!") == "nvidia jetson devices"


def test_keyword_groups_all_of_any_of():
    groups = [["jetson"], ["edgecore", "edge core"]]
    assert keyword_correct("NVIDIA Jetson via Edge Core", groups)
    assert not keyword_correct("NVIDIA Jetson", groups)


def test_keyword_matches_whole_words_only():
    assert not keyword_correct("research results", [["arc"]])
    assert keyword_correct("Intel Arc GPUs", [["intel arc"]])
    assert keyword_correct("VisionKit's library", [["visionkit"]])


def test_token_f1():
    assert abs(token_f1("the cat sat", "cat sat down") - 0.8) < 1e-9
    assert token_f1("", "cat") == 0.0
    assert token_f1("cat", "cat") == 1.0


def test_context_recall():
    assert context_recall(["a.md", "b.md", "a.md"], ["a.md", "c.md"]) == 0.5
    assert context_recall(["a.md"], []) is None


def test_citation_scores():
    assert citation_scores(["a.md", "x.md"], ["a.md", "b.md"]) == (0.5, 0.5)
    assert citation_scores([], ["a.md"]) == (None, 0.0)
    assert citation_scores(["a.md"], []) == (None, None)


def test_question_correct_handles_insufficient_category():
    assert question_correct("insufficient_evidence", [], "unknown", insufficient=True)
    assert not question_correct("insufficient_evidence", [], "Alice earns 100k", insufficient=False)
    assert not question_correct("direct", [["acme"]], "Acme", insufficient=True)
    assert question_correct("direct", [["acme"]], "Acme Technologies", insufficient=False)
