"""Deterministic answer and retrieval metrics. No LLM judge."""

import re
import string
from collections import Counter

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = str.maketrans({c: " " for c in string.punctuation})


def normalize_answer(s: str) -> str:
    """SQuAD-style: lowercase, punctuation to space, drop articles, collapse whitespace."""
    s = s.lower().translate(_PUNCT)
    return " ".join(_ARTICLES.sub(" ", s).split())


def keyword_correct(answer: str, keyword_groups: list[list[str]]) -> bool:
    """Every group needs one alternative present as whole words in the answer."""
    padded = f" {normalize_answer(answer)} "
    return all(any(f" {normalize_answer(alt)} " in padded for alt in group) for group in keyword_groups)


def question_correct(category: str, keyword_groups: list[list[str]], answer: str, insufficient: bool) -> bool:
    if category == "insufficient_evidence":
        return insufficient
    return not insufficient and keyword_correct(answer, keyword_groups)


def token_f1(pred: str, ref: str) -> float:
    p, r = normalize_answer(pred).split(), normalize_answer(ref).split()
    common = sum((Counter(p) & Counter(r)).values())
    if not p or not r or common == 0:
        return 0.0
    precision, recall = common / len(p), common / len(r)
    return 2 * precision * recall / (precision + recall)


def context_recall(retrieved_filenames: list[str], required: list[str]) -> float | None:
    if not required:
        return None
    return len(set(retrieved_filenames) & set(required)) / len(set(required))


def citation_scores(cited_filenames: list[str], required: list[str]) -> tuple[float | None, float | None]:
    """(precision, recall) over cited documents. Precision is None without citations;
    both are None when the question has no required documents."""
    if not required:
        return None, None
    cited, req = set(cited_filenames), set(required)
    precision = len(cited & req) / len(cited) if cited else None
    return precision, len(cited & req) / len(req)
