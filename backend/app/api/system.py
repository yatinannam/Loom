from fastapi import APIRouter, Depends, Query

from app.api.deps import services
from app.graph.store import GraphUnavailable
from app.services import Services

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(svc: Services = Depends(services)):
    neo4j_up = svc.graph.available()
    s = svc.settings
    return {
        "status": "ok" if neo4j_up and svc.llm_configured else "degraded",
        "neo4j": "up" if neo4j_up else "down",
        "neo4j_error": None if neo4j_up else svc.graph.last_error,
        "llm_configured": svc.llm_configured,
        "llm_base_url": s.llm_base_url,
        "models": {"extraction": s.extraction_model, "answer": s.answer_model, "query_entity": s.query_entity_model},
        "embedding_model": s.embedding_model,
    }


@router.get("/stats")
def stats(svc: Services = Depends(services)):
    try:
        graph = svc.graph.stats()
    except GraphUnavailable:
        graph = {"entities": None, "relations": None, "by_type": {}}
    return {
        "documents": len(svc.registry.list_documents()),
        "chunks": svc.vector.count_chunks(),
        "entities": graph["entities"],
        "relations": graph["relations"],
        "entities_by_type": graph["by_type"],
    }


@router.get("/activity")
def activity(limit: int = Query(20, ge=1, le=200), svc: Services = Depends(services)):
    return svc.registry.recent_activity(limit)
