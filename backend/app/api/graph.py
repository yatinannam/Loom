from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.api.deps import services
from app.api.errors import ApiError
from app.extraction.schema import ENTITY_TYPES
from app.services import Services

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _relation(r) -> dict:
    return {**asdict(r), "key": r.key}


@router.get("/stats")
def stats(svc: Services = Depends(services)):
    return svc.graph.stats()


@router.get("/entities")
def entities(q: str | None = Query(None, max_length=200), type: str | None = None,
             limit: int = Query(50, ge=1, le=500), svc: Services = Depends(services)):
    if type is not None and type not in ENTITY_TYPES:
        raise ApiError(400, "invalid_type", f"type must be one of {', '.join(ENTITY_TYPES)}")
    return [asdict(e) for e in svc.graph.find_entities(q or None, type, limit)]


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(20, ge=1, le=100),
           svc: Services = Depends(services)):
    return [asdict(e) for e in svc.graph.find_entities(q, None, limit)]


@router.get("/entities/{entity_id}")
def entity(entity_id: str, svc: Services = Depends(services)):
    e = svc.graph.get_entity(entity_id)
    if e is None:
        raise ApiError(404, "not_found", f"entity {entity_id} not found")
    mentions = svc.graph.mentions([entity_id]).get(entity_id, [])
    return {
        **asdict(e),
        "mentions": [asdict(m) for m in mentions],
        "relations": [_relation(r) for r in svc.graph.neighbors([entity_id])],
    }


@router.get("/entities/{entity_id}/neighbors")
def neighbors(entity_id: str, hops: int = Query(1, ge=1, le=2), limit: int = Query(200, ge=1, le=1000),
              svc: Services = Depends(services)):
    if svc.graph.get_entity(entity_id) is None:
        raise ApiError(404, "not_found", f"entity {entity_id} not found")
    seen, frontier, relations = {entity_id}, {entity_id}, {}
    for _ in range(hops):
        found = svc.graph.neighbors(sorted(frontier))
        nxt = set()
        for r in found:
            relations[r.key] = r
            nxt |= {r.source, r.target} - seen
        seen |= nxt
        frontier = nxt
        if len(seen) >= limit or not frontier:
            break
    ids = sorted(seen)[:limit]
    keep = set(ids)
    return {
        "entities": [asdict(e) for e in svc.graph.get_entities(ids)],
        "relations": [_relation(r) for r in relations.values() if r.source in keep and r.target in keep],
    }


@router.get("/subgraph")
def subgraph(limit: int = Query(150, ge=1, le=1000), svc: Services = Depends(services)):
    ents, rels = svc.graph.subgraph(limit)
    return {"entities": [asdict(e) for e in ents], "relations": [_relation(r) for r in rels]}
