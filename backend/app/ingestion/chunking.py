"""Character-window chunking with overlap, preferring paragraph and sentence breaks."""

from app.ingestion.parsing import Page
from app.models import ChunkRecord


def _split(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    spans = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window_floor = start + int(size * 0.7)
            para = text.rfind("\n\n", window_floor, end)
            sentence = text.rfind(". ", window_floor, end)
            if para != -1:
                end = para
            elif sentence != -1:
                end = sentence + 1
        spans.append((start, end))
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        # Begin the next chunk on a word boundary inside the overlap region.
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return spans


def chunk_pages(pages: list[Page], document_id: str, filename: str, size: int, overlap: int) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for page in pages:
        for start, end in _split(page.text, size, overlap):
            text = page.text[start:end].strip()
            if not text:
                continue
            index = len(chunks)
            chunks.append(
                ChunkRecord(
                    id=f"{document_id}:{index}",
                    document_id=document_id,
                    filename=filename,
                    page=page.number,
                    chunk_index=index,
                    text=text,
                    char_start=start,
                    char_end=end,
                )
            )
    return chunks
