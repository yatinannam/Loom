"""Wires stores, the LLM client and services together from settings."""

from dataclasses import dataclass

from app.config import Settings
from app.graph.lazy import LazyGraph
from app.graph.resolution import EntityResolver
from app.ingestion.pipeline import IngestionService
from app.llm.cache import LLMCache
from app.llm.provider import OpenAICompatibleLLM
from app.query import QueryService
from app.registry import Registry


@dataclass
class Services:
    settings: Settings
    registry: Registry
    vector: object
    graph: LazyGraph
    llm: object
    resolver: EntityResolver
    ingestion: IngestionService
    query: QueryService
    evaluation: object | None = None

    @property
    def llm_configured(self) -> bool:
        return getattr(self.llm, "configured", True)

    @classmethod
    def assemble(cls, settings, registry, vector, graph, llm, resolver, ingestion) -> "Services":
        query = QueryService(llm=llm, vector=vector, graph=graph, resolver=resolver, settings=settings,
                             registry=registry)
        services = cls(settings, registry, vector, graph, llm, resolver, ingestion, query)
        from app.evaluation.runner import EvaluationService

        services.evaluation = EvaluationService(services)
        return services


def build_services(settings: Settings) -> Services:
    import chromadb

    from app.graph.neo4j_store import Neo4jGraphStore
    from app.vector.store import ChromaVectorStore, make_embedder, model_slug

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    registry = Registry(settings.data_dir / "loom.db")
    client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    vector = ChromaVectorStore(client, make_embedder(settings.embedding_model), model_slug(settings.embedding_model))
    graph = LazyGraph(lambda: Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password))
    llm = OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout_s=settings.llm_timeout_s,
        max_rpm=settings.llm_max_rpm,
        max_retries=settings.llm_max_retries,
        cache=LLMCache(settings.data_dir / "llm_cache.db") if settings.llm_cache else None,
    )
    resolver = EntityResolver(graph, vector)
    ingestion = IngestionService(settings, registry, vector, graph, resolver, llm)
    return Services.assemble(settings, registry, vector, graph, llm, resolver, ingestion)
