"""Chunk and entity-name vector store on ChromaDB. Embeddings are computed by an
`Embedder` and passed to Chroma explicitly, so the store never depends on Chroma's
embedding-function registry."""

import re
from dataclasses import dataclass
from typing import Protocol

from app.models import ChunkRecord

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChromaOnnxEmbedder:
    """Chroma's bundled ONNX all-MiniLM-L6-v2 (CPU). Downloads the model on first use."""

    def __init__(self):
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        self._fn = ONNXMiniLM_L6_V2()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._fn(texts)]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                f"EMBEDDING_MODEL={model_name} needs sentence-transformers; run `uv sync --extra st`"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


def make_embedder(model_name: str) -> Embedder:
    if model_name == DEFAULT_EMBEDDING_MODEL:
        return ChromaOnnxEmbedder()
    return SentenceTransformerEmbedder(model_name)


def model_slug(model_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")[:40]


@dataclass
class ScoredChunk:
    chunk: ChunkRecord
    score: float


class VectorStore(Protocol):
    def upsert_chunks(self, chunks: list[ChunkRecord]) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
    def search(self, query: str, k: int, min_score: float) -> list[ScoredChunk]: ...
    def get_chunks(self, ids: list[str]) -> list[ChunkRecord]: ...
    def chunks_for_document(self, document_id: str) -> list[ChunkRecord]: ...
    def count_chunks(self) -> int: ...
    def upsert_entities(self, items: list[tuple[str, str, str]]) -> None: ...
    def delete_entities(self, ids: list[str]) -> None: ...
    def search_entities(self, query: str, k: int) -> list[tuple[str, float]]: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _to_chunk(id: str, text: str, meta: dict) -> ChunkRecord:
    page = meta.get("page", -1)
    return ChunkRecord(
        id=id,
        document_id=meta["document_id"],
        filename=meta["filename"],
        page=None if page == -1 else page,
        chunk_index=meta["chunk_index"],
        text=text,
        char_start=meta["char_start"],
        char_end=meta["char_end"],
    )


class ChromaVectorStore:
    def __init__(self, client, embedder: Embedder, collection_prefix: str):
        self.embedder = embedder
        config = {"hnsw": {"space": "cosine"}}
        self._chunks = client.get_or_create_collection(
            f"{collection_prefix}-chunks", configuration=config, embedding_function=None
        )
        self._entities = client.get_or_create_collection(
            f"{collection_prefix}-entities", configuration=config, embedding_function=None
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.embed(texts) if texts else []

    def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        self._chunks.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=self.embed([c.text for c in chunks]),
            # Chroma metadata cannot hold None; -1 marks "no page".
            metadatas=[
                {
                    "document_id": c.document_id,
                    "filename": c.filename,
                    "page": c.page if c.page is not None else -1,
                    "chunk_index": c.chunk_index,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                }
                for c in chunks
            ],
        )

    def delete_document(self, document_id: str) -> None:
        self._chunks.delete(where={"document_id": document_id})

    def search(self, query: str, k: int, min_score: float) -> list[ScoredChunk]:
        count = self._chunks.count()
        if count == 0:
            return []
        res = self._chunks.query(
            query_embeddings=self.embed([query]),
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for id, text, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            score = 1.0 - float(dist)
            if score >= min_score:
                out.append(ScoredChunk(_to_chunk(id, text, meta), score))
        return out

    def get_chunks(self, ids: list[str]) -> list[ChunkRecord]:
        if not ids:
            return []
        res = self._chunks.get(ids=list(ids), include=["documents", "metadatas"])
        found = {id: _to_chunk(id, text, meta) for id, text, meta in zip(res["ids"], res["documents"], res["metadatas"])}
        return [found[i] for i in ids if i in found]

    def chunks_for_document(self, document_id: str) -> list[ChunkRecord]:
        res = self._chunks.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        chunks = [_to_chunk(id, text, meta) for id, text, meta in zip(res["ids"], res["documents"], res["metadatas"])]
        return sorted(chunks, key=lambda c: c.chunk_index)

    def count_chunks(self) -> int:
        return self._chunks.count()

    def upsert_entities(self, items: list[tuple[str, str, str]]) -> None:
        if not items:
            return
        self._entities.upsert(
            ids=[i[0] for i in items],
            documents=[i[1] for i in items],
            embeddings=self.embed([i[1] for i in items]),
            metadatas=[{"type": i[2]} for i in items],
        )

    def delete_entities(self, ids: list[str]) -> None:
        if ids:
            self._entities.delete(ids=list(ids))

    def search_entities(self, query: str, k: int) -> list[tuple[str, float]]:
        count = self._entities.count()
        if count == 0:
            return []
        res = self._entities.query(
            query_embeddings=self.embed([query]), n_results=min(k, count), include=["distances"]
        )
        return [(id, 1.0 - float(d)) for id, d in zip(res["ids"][0], res["distances"][0])]
