"""Shared data models."""

from pydantic import BaseModel


class ChunkRecord(BaseModel):
    id: str
    document_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    char_start: int
    char_end: int
