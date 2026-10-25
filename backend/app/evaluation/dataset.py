import json
from pathlib import Path

from pydantic import BaseModel


class Question(BaseModel):
    id: str
    category: str
    question: str
    reference_answer: str
    answer_keywords: list[list[str]]
    required_documents: list[str]


def load_questions(path: Path) -> list[Question]:
    return [Question.model_validate(q) for q in json.loads(Path(path).read_text(encoding="utf-8"))]
