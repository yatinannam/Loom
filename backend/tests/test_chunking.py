from app.ingestion.chunking import chunk_pages
from app.ingestion.parsing import Page


def sentences(n: int) -> str:
    return " ".join(f"Sentence number {i:03d} talks about item {i}." for i in range(n))


def test_long_text_splits_with_overlap():
    text = sentences(60)  # about 2500 characters
    assert 2300 < len(text) < 2700
    chunks = chunk_pages([Page(None, text)], "doc", "a.txt", size=1000, overlap=150)
    assert len(chunks) == 3
    for a, b in zip(chunks, chunks[1:]):
        assert b.char_start < a.char_end  # overlap
        assert a.char_end - b.char_start <= 150 + 1
    assert all(len(c.text) <= 1000 for c in chunks)
    assert chunks[-1].char_end == len(text)


def test_chunk_ids_and_metadata():
    chunks = chunk_pages([Page(None, sentences(60))], "doc", "a.txt", size=1000, overlap=150)
    assert [c.id for c in chunks] == ["doc:0", "doc:1", "doc:2"]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert all(c.document_id == "doc" and c.filename == "a.txt" for c in chunks)


def test_chunks_break_at_sentence_boundary():
    chunks = chunk_pages([Page(None, sentences(60))], "doc", "a.txt", size=1000, overlap=150)
    assert chunks[0].text.endswith(".")


def test_chunks_never_span_pages():
    pages = [Page(1, "Page one text."), Page(2, "Page two text.")]
    chunks = chunk_pages(pages, "doc", "a.pdf", size=1000, overlap=150)
    assert [(c.page, c.text) for c in chunks] == [(1, "Page one text."), (2, "Page two text.")]
    assert [c.id for c in chunks] == ["doc:0", "doc:1"]


def test_short_text_is_one_chunk():
    chunks = chunk_pages([Page(None, "Alice leads the team.")], "doc", "a.md", size=1000, overlap=150)
    assert len(chunks) == 1
    assert chunks[0].text == "Alice leads the team."
    assert (chunks[0].char_start, chunks[0].char_end) == (0, 21)
