import json

import pytest

from app.extraction.extractor import ExtractionParseError, extract_chunk, validate_extraction

TEXT = "Alice works at Acme Technologies and leads the Autonomous Systems team."


def payload(entities=None, relations=None, **extra):
    body = {"entities": entities or [], **extra}
    if relations is not None:
        body["relations"] = relations
    return json.dumps(body)


ALICE = {"name": "Alice", "type": "PERSON"}
ACME = {"name": "Acme Technologies", "type": "ORGANIZATION"}
WORKS_AT = {"source": "Alice", "target": "Acme Technologies", "type": "WORKS_AT",
            "evidence": "Alice works at Acme Technologies", "confidence": 0.9}


def test_malformed_json_raises():
    with pytest.raises(ExtractionParseError):
        validate_extraction("{not json", TEXT)


def test_non_object_json_raises():
    with pytest.raises(ExtractionParseError):
        validate_extraction("[1, 2]", TEXT)


def test_missing_relations_key_gives_empty_list():
    result, warnings = validate_extraction(payload([ALICE]), TEXT)
    assert [e.name for e in result.entities] == ["Alice"]
    assert result.relations == []


def test_unknown_entity_type_becomes_other():
    result, _ = validate_extraction(payload([{"name": "Thing", "type": "GADGET"}]), TEXT)
    assert result.entities[0].type == "OTHER"


def test_relation_type_coerced_to_upper_snake():
    rel = {**WORKS_AT, "type": "works at"}
    result, _ = validate_extraction(payload([ALICE, ACME], [rel]), TEXT)
    assert result.relations[0].type == "WORKS_AT"


def test_confidence_clamped():
    rel = {**WORKS_AT, "confidence": 3}
    result, _ = validate_extraction(payload([ALICE, ACME], [rel]), TEXT)
    assert result.relations[0].confidence == 1.0


def test_relation_with_unknown_endpoint_dropped_with_warning():
    rel = {**WORKS_AT, "target": "Initech"}
    result, warnings = validate_extraction(payload([ALICE, ACME], [rel]), TEXT)
    assert result.relations == []
    assert any("Initech" in w for w in warnings)


def test_relation_with_unsupported_evidence_dropped():
    rel = {**WORKS_AT, "evidence": "Alice founded Acme Technologies in 1999 with Bob"}
    result, warnings = validate_extraction(payload([ALICE, ACME], [rel]), TEXT)
    assert result.relations == []
    assert any("evidence" in w for w in warnings)


def test_evidence_with_case_and_whitespace_difference_kept():
    rel = {**WORKS_AT, "evidence": "alice   WORKS at acme technologies"}
    result, _ = validate_extraction(payload([ALICE, ACME], [rel]), TEXT)
    assert len(result.relations) == 1


def test_relation_endpoint_matched_by_alias():
    acme = {**ACME, "aliases": ["Acme"]}
    rel = {**WORKS_AT, "target": "Acme"}
    result, _ = validate_extraction(payload([ALICE, acme], [rel]), TEXT)
    assert result.relations[0].target == "Acme Technologies"


def test_entity_without_name_dropped():
    result, warnings = validate_extraction(payload([{"type": "PERSON"}, ALICE]), TEXT)
    assert [e.name for e in result.entities] == ["Alice"]
    assert warnings


def test_self_relation_dropped():
    rel = {**WORKS_AT, "target": "Alice"}
    result, _ = validate_extraction(payload([ALICE], [rel]), TEXT)
    assert result.relations == []


class SequenceLLM:
    def __init__(self, texts):
        self.texts = list(texts)
        self.prompts = []

    def complete(self, messages, *, model, json_mode=False, max_tokens=1024):
        from app.llm.provider import LLMResponse, LLMUsage

        self.prompts.append(messages)
        return LLMResponse(self.texts.pop(0), LLMUsage(model, 1, 1, 1.0, False))


def test_retry_once_on_parse_error():
    llm = SequenceLLM(["{oops", payload([ALICE, ACME], [WORKS_AT])])
    result, warnings, usage = extract_chunk(llm, "m", TEXT)
    assert len(llm.prompts) == 2
    assert len(result.relations) == 1
    assert len(usage) == 2
    assert TEXT in llm.prompts[0][-1]["content"]


def test_two_parse_errors_raise():
    llm = SequenceLLM(["{oops", "{still bad"])
    with pytest.raises(ExtractionParseError):
        extract_chunk(llm, "m", TEXT)


class RaisingThenLLM(SequenceLLM):
    def complete(self, messages, *, model, json_mode=False, max_tokens=1024):
        item = self.texts[0]
        if isinstance(item, Exception):
            self.texts.pop(0)
            self.prompts.append(messages)
            raise item
        return super().complete(messages, model=model, json_mode=json_mode, max_tokens=max_tokens)


def test_provider_json_failure_is_retried_like_a_parse_error():
    from app.llm.provider import LLMInvalidJSON

    llm = RaisingThenLLM([LLMInvalidJSON("json_validate_failed"), payload([ALICE, ACME], [WORKS_AT])])
    result, _, _ = extract_chunk(llm, "m", TEXT)
    assert len(result.relations) == 1
    assert len(llm.prompts) == 2


def test_provider_json_failure_twice_becomes_parse_error():
    from app.llm.provider import LLMInvalidJSON

    llm = RaisingThenLLM([LLMInvalidJSON("json_validate_failed"), LLMInvalidJSON("json_validate_failed")])
    with pytest.raises(ExtractionParseError):
        extract_chunk(llm, "m", TEXT)
