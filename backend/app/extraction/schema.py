"""Schema for LLM entity and relation extraction output."""

import re

from pydantic import BaseModel, Field, field_validator

ENTITY_TYPES = (
    "PERSON",
    "ORGANIZATION",
    "TEAM",
    "PROJECT",
    "PRODUCT",
    "TECHNOLOGY",
    "LOCATION",
    "EVENT",
    "CONCEPT",
    "OTHER",
)


class ExtractedEntity(BaseModel):
    name: str = Field(min_length=1)
    type: str = "OTHER"
    aliases: list[str] = []
    description: str = ""

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty name")
        return v

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v) -> str:
        v = str(v or "").strip().upper()
        return v if v in ENTITY_TYPES else "OTHER"

    @field_validator("aliases", mode="before")
    @classmethod
    def _clean_aliases(cls, v) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(a).strip() for a in v if str(a).strip()]

    @field_validator("description", mode="before")
    @classmethod
    def _description(cls, v) -> str:
        return str(v or "").strip()


class ExtractedRelation(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: str = Field(min_length=1)
    evidence: str = ""
    confidence: float = 0.7

    @field_validator("type", mode="before")
    @classmethod
    def _upper_snake(cls, v) -> str:
        v = re.sub(r"[^A-Za-z0-9]+", "_", str(v or "")).strip("_").upper()
        if not v:
            raise ValueError("empty relation type")
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.7
        return min(max(v, 0.0), 1.0)


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = []
    relations: list[ExtractedRelation] = []
