"""Grounded answer generation from retrieved evidence, with citation validation."""

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from app.llm.provider import LLMBadResponse, LLMProvider, LLMUsage
from app.retrieval.types import GraphPath, RetrievalResult, RetrievedChunk

INSUFFICIENT_MESSAGE = "The indexed documents do not contain enough evidence to answer this question."

SYSTEM_PROMPT = """You answer questions using only the evidence provided.
Rules:
- Use only facts stated in the evidence blocks [S#] and graph facts [P#]. No outside knowledge.
- Cite every block you rely on by its id, for example "S1" or "P2".
- If the evidence does not answer the question, set insufficient_evidence to true and say what is missing.
- If evidence blocks contradict each other, describe the conflict in conflicts instead of choosing silently.
- explanation is two or three sentences connecting the cited facts. Do not include private reasoning.
Reply with one JSON object:
{"answer": str, "explanation": str, "citations": [str], "insufficient_evidence": bool, "conflicts": [str]}"""


@dataclass
class Citation:
    id: str
    kind: Literal["chunk", "path"]
    chunk_id: str | None = None
    document_id: str | None = None
    filename: str | None = None
    page: int | None = None
    path: str | None = None
    filenames: list[str] = field(default_factory=list)


@dataclass
class Answer:
    answer: str
    explanation: str
    citations: list[Citation]
    insufficient_evidence: bool
    conflicts: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    grounded: bool = True
    usage: LLMUsage | None = None


def build_messages(question: str, chunks: list[RetrievedChunk], paths: list[GraphPath]) -> list[dict]:
    source_ids = {c.chunk.id: f"S{i}" for i, c in enumerate(chunks, start=1)}
    lines = [f"Question: {question}", "", "Evidence:"]
    for i, c in enumerate(chunks, start=1):
        where = f"{c.chunk.filename}" + (f", page {c.chunk.page}" if c.chunk.page is not None else "")
        lines += [f"[S{i}] ({where}, chunk {c.chunk.id})", c.chunk.text, ""]
    if paths:
        lines.append("Graph facts (entity relationship paths extracted from the documents):")
        for i, p in enumerate(paths, start=1):
            refs = [source_ids[c] for c in p.chunk_ids if c in source_ids]
            lines.append(f"[P{i}] {p.render()}" + (f" (supported by {', '.join(refs)})" if refs else ""))
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n".join(lines)}]


def parse_answer(raw: str, chunks: list[RetrievedChunk], paths: list[GraphPath]) -> Answer:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMBadResponse(f"answer is not a JSON object: {exc}") from exc

    by_chunk_id = {c.chunk.id: c.chunk for c in chunks}
    citations: list[Citation] = []
    invalid: list[str] = []
    for item in data.get("citations") or []:
        cid = re.sub(r"[\[\]\s]", "", str(item)).upper()
        kind, num = cid[:1], cid[1:]
        index = int(num) - 1 if num.isdigit() else -1
        if kind == "S" and 0 <= index < len(chunks):
            c = chunks[index].chunk
            citations.append(Citation(cid, "chunk", c.id, c.document_id, c.filename, c.page, filenames=[c.filename]))
        elif kind == "P" and 0 <= index < len(paths):
            p = paths[index]
            names = list(dict.fromkeys(by_chunk_id[c].filename for c in p.chunk_ids if c in by_chunk_id))
            citations.append(Citation(cid, "path", path=p.render(), filenames=names))
        else:
            invalid.append(cid)
    citations = list({c.id: c for c in citations}.values())

    insufficient = bool(data.get("insufficient_evidence", False))
    return Answer(
        answer=str(data.get("answer") or ""),
        explanation=str(data.get("explanation") or ""),
        citations=citations,
        insufficient_evidence=insufficient,
        conflicts=[str(c) for c in data.get("conflicts") or []],
        invalid_citations=invalid,
        grounded=bool(citations) or insufficient,
    )


def generate_answer(llm: LLMProvider, model: str, question: str, retrieval: RetrievalResult) -> Answer:
    if not retrieval.chunks and not retrieval.paths:
        return Answer(answer=INSUFFICIENT_MESSAGE, explanation=retrieval.route_reason, citations=[],
                      insufficient_evidence=True)
    resp = llm.complete(build_messages(question, retrieval.chunks, retrieval.paths), model=model,
                        json_mode=True, max_tokens=800)
    answer = parse_answer(resp.text, retrieval.chunks, retrieval.paths)
    answer.usage = resp.usage
    return answer
