import json

import pytest

from app.answer.generator import build_messages, generate_answer, parse_answer
from app.llm.provider import LLMBadResponse
from app.models import ChunkRecord
from app.retrieval.types import GraphPath, PathStep, RetrievalResult, RetrievedChunk
from tests.fakes import FakeLLM


def chunk(i, filename, page=None):
    rec = ChunkRecord(id=f"d{i}:0", document_id=f"d{i}", filename=filename, page=page, chunk_index=0,
                      text=f"text {i}", char_start=0, char_end=6)
    return RetrievedChunk(chunk=rec, score=0.5, sources={"vector": {"rank": i, "score": 0.5}})


CHUNKS = [chunk(1, "a.md"), chunk(2, "b.pdf", page=3)]
PATHS = [GraphPath([PathStep("x", "X", "USES", "y", "Y", True)], 0.7, ["d2:0"])]


def raw(**kw):
    body = {"answer": "Y", "explanation": "X uses Y.", "citations": ["S1"], "insufficient_evidence": False,
            "conflicts": []}
    body.update(kw)
    return json.dumps(body)


def test_prompt_numbers_evidence_and_paths():
    content = build_messages("What does X use?", CHUNKS, PATHS)[-1]["content"]
    assert "[S1]" in content and "a.md" in content
    assert "[S2]" in content and "page 3" in content
    assert "[P1] X -[USES]-> Y" in content
    assert "Question: What does X use?" in content


def test_valid_citations_resolve():
    ans = parse_answer(raw(citations=["S2", "[P1]"]), CHUNKS, PATHS)
    s2, p1 = ans.citations
    assert (s2.kind, s2.filename, s2.page, s2.chunk_id) == ("chunk", "b.pdf", 3, "d2:0")
    assert (p1.kind, p1.path, p1.filenames) == ("path", "X -[USES]-> Y", ["b.pdf"])
    assert ans.grounded is True


def test_unknown_citation_removed():
    ans = parse_answer(raw(citations=["S1", "S9", "P4"]), CHUNKS, PATHS)
    assert [c.id for c in ans.citations] == ["S1"]
    assert ans.invalid_citations == ["S9", "P4"]


def test_no_valid_citation_is_ungrounded():
    ans = parse_answer(raw(citations=["S9"]), CHUNKS, PATHS)
    assert ans.grounded is False


def test_insufficient_without_citations_is_not_flagged_ungrounded():
    ans = parse_answer(raw(citations=[], insufficient_evidence=True), CHUNKS, PATHS)
    assert ans.insufficient_evidence is True
    assert ans.grounded is True


def test_conflicts_passed_through():
    ans = parse_answer(raw(conflicts=["S1 says A, S2 says B"]), CHUNKS, PATHS)
    assert ans.conflicts == ["S1 says A, S2 says B"]


def test_malformed_answer_raises():
    with pytest.raises(LLMBadResponse):
        parse_answer("not json", CHUNKS, PATHS)


def test_empty_retrieval_skips_llm():
    llm = FakeLLM([])
    ans = generate_answer(llm, "m", "q", RetrievalResult(mode="graph", chunks=[], route_reason="no seed"))
    assert llm.calls == []
    assert ans.insufficient_evidence is True
    assert ans.citations == []
