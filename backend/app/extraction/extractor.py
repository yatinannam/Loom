"""LLM-based entity and relation extraction with validation."""

import json

from pydantic import ValidationError

from app.extraction.normalize import evidence_supported, normalize_name
from app.extraction.schema import ENTITY_TYPES, ExtractedEntity, ExtractedRelation, ExtractionResult
from app.llm.provider import LLMInvalidJSON, LLMProvider, LLMUsage

SYSTEM_PROMPT = f"""You extract a knowledge graph from text.
Return one JSON object with exactly two keys, "entities" and "relations".

entities: list of objects {{"name", "type", "aliases", "description"}}
- type is one of: {", ".join(ENTITY_TYPES)}
- name is the most complete form used in the text; aliases are other forms used in the text
- description is one short sentence based only on the text

relations: list of objects {{"source", "target", "type", "evidence", "confidence"}}
- source and target are entity names from your entities list
- type is a short verb phrase in UPPER_SNAKE_CASE, for example WORKS_AT, LEADS, DEVELOPED, USES, DEPLOYED_ON, LOCATED_IN, PART_OF, MAINTAINS
- evidence is the exact sentence from the text that states the relation
- confidence is a number from 0 to 1

Only include relations the text states explicitly. Do not infer, guess or use outside knowledge.
If the text has no entities, return {{"entities": [], "relations": []}}."""


class ExtractionParseError(Exception):
    pass


def validate_extraction(raw: str, chunk_text: str) -> tuple[ExtractionResult, list[str]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionParseError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionParseError("response JSON is not an object")

    warnings: list[str] = []
    entities: list[ExtractedEntity] = []
    names: dict[str, str] = {}  # normalized name or alias -> canonical entity name
    for item in data.get("entities") or []:
        try:
            entity = ExtractedEntity.model_validate(item)
        except ValidationError as exc:
            warnings.append(f"dropped entity {item!r}: {exc.errors()[0]['msg']}")
            continue
        entities.append(entity)
        for form in [entity.name, *entity.aliases]:
            names.setdefault(normalize_name(form), entity.name)

    relations: list[ExtractedRelation] = []
    for item in data.get("relations") or []:
        try:
            rel = ExtractedRelation.model_validate(item)
        except ValidationError as exc:
            warnings.append(f"dropped relation {item!r}: {exc.errors()[0]['msg']}")
            continue
        source = names.get(normalize_name(rel.source))
        target = names.get(normalize_name(rel.target))
        label = f"{rel.source} -[{rel.type}]-> {rel.target}"
        if source is None or target is None:
            missing = rel.source if source is None else rel.target
            warnings.append(f"dropped relation {label}: endpoint {missing!r} is not an extracted entity")
            continue
        if source == target:
            warnings.append(f"dropped relation {label}: source and target are the same entity")
            continue
        if not evidence_supported(rel.evidence, chunk_text):
            warnings.append(f"dropped relation {label}: evidence not found in the chunk text")
            continue
        relations.append(rel.model_copy(update={"source": source, "target": target}))

    return ExtractionResult(entities=entities, relations=relations), warnings


def extract_chunk(
    llm: LLMProvider, model: str, chunk_text: str
) -> tuple[ExtractionResult, list[str], list[LLMUsage]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Text:\n{chunk_text}"},
    ]
    usages: list[LLMUsage] = []

    def attempt(msgs: list[dict]) -> tuple[ExtractionResult, list[str]]:
        try:
            resp = llm.complete(msgs, model=model, json_mode=True, max_tokens=2048)
        except LLMInvalidJSON as exc:  # provider-side JSON failure: same handling as unparseable output
            raise ExtractionParseError(str(exc)) from exc
        usages.append(resp.usage)
        return validate_extraction(resp.text, chunk_text)

    try:
        result, warnings = attempt(messages)
    except ExtractionParseError as exc:
        retry = messages + [
            {"role": "user", "content": f"Your previous reply was invalid ({exc}). "
                                        f"Reply with only the JSON object for the same text:\n{chunk_text}"},
        ]
        result, warnings = attempt(retry)
    return result, warnings, usages
