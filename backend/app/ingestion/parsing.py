"""Upload validation and text extraction for PDF, TXT and Markdown files."""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


@dataclass
class Page:
    number: int | None
    text: str


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NoExtractableText(Exception):
    pass


def validate_upload(filename: str, data: bytes, max_bytes: int) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UploadRejected("unsupported_type", f"unsupported file type {ext or '(none)'}; use .pdf, .txt or .md")
    if len(data) > max_bytes:
        raise UploadRejected("too_large", f"file is {len(data)} bytes; the limit is {max_bytes} bytes")
    if not data:
        raise UploadRejected("empty_file", "file is empty")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise UploadRejected("invalid_pdf", "file has a .pdf extension but is not a PDF")
    return ext


def document_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def parse_file(path: Path) -> list[Page]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(path)
            pages = [Page(i, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages, start=1)]
        except PdfReadError as exc:
            raise NoExtractableText(f"PDF could not be read: {exc}") from exc
    else:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip()
        pages = [Page(None, text)]
    pages = [p for p in pages if p.text]
    if not pages:
        raise NoExtractableText("no extractable text (scanned PDFs without a text layer are not supported)")
    return pages
