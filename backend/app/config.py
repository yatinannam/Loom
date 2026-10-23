"""Application settings, read from environment variables and the repository `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # Storage
    data_dir: Path = REPO_ROOT / "data" / "runtime"
    benchmark_dir: Path = REPO_ROOT / "data" / "benchmark"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "loom-password"

    # LLM
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    extraction_model: str = "llama-3.3-70b-versatile"
    answer_model: str = "llama-3.1-8b-instant"
    query_entity_model: str = "llama-3.1-8b-instant"
    llm_max_rpm: int = 25
    llm_max_retries: int = 5
    llm_timeout_s: float = 60
    llm_cache: bool = True
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Ingestion
    max_upload_mb: int = 10
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Retrieval
    max_evidence_chunks: int = 6
    vector_min_score: float = 0.2
    entity_min_score: float = 0.5
    max_seed_entities: int = 5
    max_hops: int = Field(3, ge=1, le=4)
    max_node_degree: int = 50
    max_paths: int = 200
    hop_decay: float = 0.85
    path_min_score: float = 0.1
    top_paths: int = 8
    rrf_k: int = 60
    vector_weight: float = 1.0
    graph_weight: float = 1.0

    # API
    cors_origins: str = "http://localhost:3000"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
