from fastapi import Request

from app.api.errors import ApiError
from app.services import Services


def services(request: Request) -> Services:
    return request.app.state.services


def require_ingest_ready(svc: Services) -> None:
    """Ingestion needs both the LLM and the graph; refuse up front instead of failing in the background."""
    if not svc.llm_configured:
        raise ApiError(503, "llm_not_configured", "LLM_API_KEY is not set; ingestion needs an LLM provider key")
    svc.graph.get()
