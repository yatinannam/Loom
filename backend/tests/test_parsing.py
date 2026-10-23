import pytest

from app.ingestion.parsing import (
    NoExtractableText,
    UploadRejected,
    document_id_for,
    parse_file,
    validate_upload,
)
from tests.pdf_fixture import make_pdf


def test_rejects_unsupported_extension():
    with pytest.raises(UploadRejected) as exc:
        validate_upload("tool.exe", b"MZ", 1000)
    assert exc.value.code == "unsupported_type"


def test_rejects_oversize_file():
    with pytest.raises(UploadRejected) as exc:
        validate_upload("a.txt", b"x" * 11, 10)
    assert exc.value.code == "too_large"


def test_rejects_pdf_without_magic_bytes():
    with pytest.raises(UploadRejected) as exc:
        validate_upload("a.pdf", b"not a pdf", 1000)
    assert exc.value.code == "invalid_pdf"


def test_accepts_markdown_case_insensitive():
    assert validate_upload("Notes.MD", b"# hi", 1000) == ".md"


def test_document_id_is_stable_content_hash():
    assert document_id_for(b"abc") == document_id_for(b"abc")
    assert document_id_for(b"abc") != document_id_for(b"abd")
    assert len(document_id_for(b"abc")) == 16


def test_pdf_pages_keep_numbers(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf(["Alice leads the team.", "EdgeCore runs on Jetson."]))
    pages = parse_file(path)
    assert [p.number for p in pages] == [1, 2]
    assert "Alice" in pages[0].text
    assert "Jetson" in pages[1].text


def test_text_file_has_no_page_number(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Hello world", encoding="utf-8")
    pages = parse_file(path)
    assert len(pages) == 1
    assert pages[0].number is None
    assert pages[0].text == "Hello world"


def test_empty_text_file_raises(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(NoExtractableText):
        parse_file(path)


def test_pdf_without_text_layer_raises(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_pdf([""]))
    with pytest.raises(NoExtractableText):
        parse_file(path)
