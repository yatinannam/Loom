"""Ingestion: store upload, parse, chunk, embed, extract, resolve and persist."""

import logging
from pathlib import Path

from app.config import Settings
from app.extraction.extractor import ExtractionParseError, extract_chunk
from app.extraction.normalize import entity_id
from app.graph.resolution import EntityResolver
from app.graph.store import Entity, GraphStore, Mention
from app.ingestion.chunking import chunk_pages
from app.ingestion.parsing import SUPPORTED_EXTENSIONS, document_id_for, parse_file, validate_upload
from app.llm.provider import LLMProvider
from app.registry import DocumentRow, Registry
from app.vector.store import VectorStore

log = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        registry: Registry,
        vector: VectorStore,
        graph: GraphStore,
        resolver: EntityResolver,
        llm: LLMProvider,
    ):
        self.settings = settings
        self.registry = registry
        self.vector = vector
        self.graph = graph
        self.resolver = resolver
        self.llm = llm

    def _path(self, doc: DocumentRow) -> Path:
        return self.settings.uploads_dir / f"{doc.id}{Path(doc.filename).suffix.lower()}"

    def add_file(self, filename: str, data: bytes) -> DocumentRow:
        """Validate and store an upload. Identical content maps to the same document."""
        ext = validate_upload(filename, data, self.settings.max_upload_mb * 1024 * 1024)
        doc_id = document_id_for(data)
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.uploads_dir / f"{doc_id}{ext}").write_bytes(data)
        return self.registry.upsert_document(doc_id, Path(filename).name, SUPPORTED_EXTENSIONS[ext], len(data))

    def _remove_contribution(self, document_id: str) -> None:
        self.vector.delete_document(document_id)
        removed = self.graph.remove_document(document_id)
        self.vector.delete_entities(removed)
        self.graph.recompute_degrees()

    def ingest(self, document_id: str) -> None:
        """Ingest one stored document. Never raises; the outcome is the document status."""
        doc = self.registry.get_document(document_id)
        if doc is None:
            log.warning("ingest requested for unknown document %s", document_id)
            return
        self.registry.set_status(document_id, "processing")
        self.registry.clear_extraction_errors(document_id)
        try:
            counts = self._ingest(doc)
        except Exception as exc:
            code = getattr(exc, "code", type(exc).__name__)
            message = f"{code}: {exc}"
            log.error("ingestion failed for %s (%s): %s", doc.filename, document_id, message)
            try:
                self._remove_contribution(document_id)
            except Exception:
                log.exception("cleanup after failed ingestion of %s also failed", document_id)
            self.registry.set_status(document_id, "failed", error=message)
            self.registry.log_activity("ingest", f"Ingestion of {doc.filename} failed: {message}")
            return
        self.registry.set_status(document_id, "ingested", **counts)
        self.registry.log_activity(
            "ingest",
            f"Ingested {doc.filename}: {counts['chunk_count']} chunks, "
            f"{counts['entity_count']} entities, {counts['relation_count']} relations",
        )

    def _ingest(self, doc: DocumentRow) -> dict:
        self._remove_contribution(doc.id)
        pages = parse_file(self._path(doc))
        chunks = chunk_pages(pages, doc.id, doc.filename, self.settings.chunk_size, self.settings.chunk_overlap)
        self.vector.upsert_chunks(chunks)
        self.resolver.refresh()

        touched: set[str] = set()
        relations: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            try:
                result, warnings, _ = extract_chunk(self.llm, self.settings.extraction_model, chunk.text)
            except ExtractionParseError as exc:
                self.registry.add_extraction_error(doc.id, chunk.id, str(exc), None)
                continue
            for warning in warnings:
                self.registry.add_extraction_error(doc.id, chunk.id, warning, None)

            mention = Mention(chunk.id, doc.id, doc.filename, chunk.page)
            ids: dict[str, str] = {}
            for ent in result.entities:
                eid = self.resolver.resolve_ingest(ent.name, ent.aliases) or entity_id(ent.name)
                # The extracted name goes in as an alias too; the store drops it if it is the node's name.
                self.graph.upsert_entity(
                    Entity(eid, ent.name, ent.type, [ent.name, *ent.aliases], ent.description), mention
                )
                self.resolver.register(eid, [ent.name, *ent.aliases])
                ids[ent.name] = eid
                touched.add(eid)
            for rel in result.relations:
                src, tgt = ids[rel.source], ids[rel.target]
                if src == tgt:
                    continue
                self.graph.upsert_relation(src, tgt, rel.type, mention, rel.evidence, rel.confidence)
                relations.add((src, rel.type, tgt))

        entities = self.graph.get_entities(sorted(touched))
        self.vector.upsert_entities(
            [(e.id, f"{e.name}: {e.description}" if e.description else e.name, e.type) for e in entities]
        )
        self.graph.recompute_degrees()
        page_numbers = [p.number for p in pages if p.number is not None]
        return {
            "pages": max(page_numbers) if page_numbers else None,
            "chunk_count": len(chunks),
            "entity_count": len(touched),
            "relation_count": len(relations),
        }

    def remove(self, document_id: str) -> None:
        doc = self.registry.get_document(document_id)
        if doc is None:
            return
        self._remove_contribution(document_id)
        self._path(doc).unlink(missing_ok=True)
        self.registry.delete_document(document_id)
        self.registry.log_activity("delete", f"Removed {doc.filename}")
