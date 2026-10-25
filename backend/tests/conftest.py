import uuid
from dataclasses import dataclass
from pathlib import Path

import chromadb
import pytest

from app.config import REPO_ROOT, Settings
from app.graph.memory_store import InMemoryGraphStore
from app.graph.resolution import EntityResolver
from app.ingestion.pipeline import IngestionService
from app.registry import Registry
from app.vector.store import ChromaVectorStore
from tests.fakes import HashEmbedder
from tests.fixtures.demo_llm import demo_fake_llm

DEMO_DIR = REPO_ROOT / "data" / "demo"


@dataclass
class Env:
    settings: Settings
    registry: Registry
    vector: ChromaVectorStore
    graph: InMemoryGraphStore
    resolver: EntityResolver
    llm: object
    ingestion: IngestionService

    def add_and_ingest(self, path: Path) -> str:
        row = self.ingestion.add_file(path.name, path.read_bytes())
        self.ingestion.ingest(row.id)
        return row.id


def make_env(tmp_path, llm=None, **overrides) -> Env:
    settings = Settings(_env_file=None, data_dir=tmp_path, **overrides)
    registry = Registry(tmp_path / "loom.db")
    vector = ChromaVectorStore(chromadb.EphemeralClient(), HashEmbedder(), collection_prefix=uuid.uuid4().hex[:8])
    graph = InMemoryGraphStore()
    resolver = EntityResolver(graph, vector)
    llm = llm or demo_fake_llm()
    ingestion = IngestionService(settings, registry, vector, graph, resolver, llm)
    return Env(settings, registry, vector, graph, resolver, llm, ingestion)


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path)


@pytest.fixture
def demo_env(tmp_path):
    env = make_env(tmp_path)
    env.doc_ids = {p.name: env.add_and_ingest(p) for p in sorted(DEMO_DIR.glob("*.md"))}
    return env
