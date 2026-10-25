"""Entity name normalization and evidence support checks."""

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

EVIDENCE_TOKEN_OVERLAP = 0.8


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("_", " ")
    return _SPACE.sub(" ", _PUNCT.sub(" ", text)).strip()


def normalize_name(name: str) -> str:
    key = _clean(name)
    return key[4:] if key.startswith("the ") else key


def entity_id(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def _tokens(text: str) -> set[str]:
    return set(_clean(text).split())


def evidence_supported(evidence: str, text: str) -> bool:
    """True when the evidence occurs in the text (ignoring case, punctuation and
    whitespace) or shares at least 80% of its tokens with one sentence of the text."""
    ev = _clean(evidence)
    if not ev:
        return False
    if ev in _clean(text):
        return True
    ev_tokens = set(ev.split())
    for sentence in _SENTENCE.split(text):
        if len(ev_tokens & _tokens(sentence)) / len(ev_tokens) >= EVIDENCE_TOKEN_OVERLAP:
            return True
    return False
