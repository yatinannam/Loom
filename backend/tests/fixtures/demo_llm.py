"""Canned LLM responses for the three-document demo corpus (data/demo)."""

import json

from app.retrieval.graph import QUERY_ENTITY_PREFIX
from tests.fakes import FakeLLM

EMPLOYEE_SENTENCE = "Alice works at Acme Technologies and leads the Autonomous Systems team."
PROJECT_SENTENCE = "The Autonomous Systems team developed Project Falcon, which uses the EdgeCore platform."
TECH_SENTENCE = "EdgeCore is maintained by a separate infrastructure team and is deployed on NVIDIA Jetson devices."

ALICE_QUESTION = (
    "Which hardware platform is used by the project led by Alice's team, "
    "and which technology connects the project to that hardware?"
)


def _extraction(entities, relations) -> str:
    return json.dumps({"entities": entities, "relations": relations})


EXTRACTIONS = {
    EMPLOYEE_SENTENCE: _extraction(
        [
            {"name": "Alice", "type": "PERSON", "description": "Leads the Autonomous Systems team."},
            {"name": "Acme Technologies", "type": "ORGANIZATION", "aliases": ["Acme"]},
            {"name": "Autonomous Systems", "type": "TEAM", "aliases": ["Autonomous Systems team"]},
        ],
        [
            {"source": "Alice", "target": "Acme Technologies", "type": "WORKS_AT",
             "evidence": EMPLOYEE_SENTENCE, "confidence": 0.95},
            {"source": "Alice", "target": "Autonomous Systems", "type": "LEADS",
             "evidence": EMPLOYEE_SENTENCE, "confidence": 0.95},
        ],
    ),
    PROJECT_SENTENCE: _extraction(
        [
            {"name": "Autonomous Systems team", "type": "TEAM"},
            {"name": "Project Falcon", "type": "PROJECT", "aliases": ["Falcon"]},
            {"name": "EdgeCore", "type": "TECHNOLOGY", "aliases": ["EdgeCore platform"]},
        ],
        [
            {"source": "Autonomous Systems team", "target": "Project Falcon", "type": "DEVELOPED",
             "evidence": PROJECT_SENTENCE, "confidence": 0.9},
            {"source": "Project Falcon", "target": "EdgeCore", "type": "USES",
             "evidence": PROJECT_SENTENCE, "confidence": 0.9},
        ],
    ),
    TECH_SENTENCE: _extraction(
        [
            {"name": "EdgeCore", "type": "TECHNOLOGY", "description": "Platform deployed on NVIDIA Jetson."},
            {"name": "infrastructure team", "type": "TEAM"},
            {"name": "NVIDIA Jetson", "type": "PRODUCT", "description": "Edge hardware devices."},
        ],
        [
            {"source": "infrastructure team", "target": "EdgeCore", "type": "MAINTAINS",
             "evidence": TECH_SENTENCE, "confidence": 0.85},
            {"source": "EdgeCore", "target": "NVIDIA Jetson", "type": "DEPLOYED_ON",
             "evidence": TECH_SENTENCE, "confidence": 0.9},
        ],
    ),
}


QUERY_ENTITIES = [
    (f"{QUERY_ENTITY_PREFIX}\n{ALICE_QUESTION}",
     json.dumps({"entities": ["Alice", "Alice's team", "project", "hardware platform"]})),
    # Any other question: no entities named.
    (QUERY_ENTITY_PREFIX, json.dumps({"entities": []})),
]


def demo_responses() -> list[tuple[str, object]]:
    return [*EXTRACTIONS.items(), *QUERY_ENTITIES]


def demo_fake_llm(extra: list[tuple[str, object]] | None = None) -> FakeLLM:
    """Extra responses are matched first, so tests can override or add prompts."""
    return FakeLLM([*(extra or []), *demo_responses()])
