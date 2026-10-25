from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import services
from app.api.errors import ApiError
from app.query import QueryResponse
from app.services import Services

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["standard", "graph", "hybrid"] = "hybrid"
    overrides: dict[str, float | int] | None = None


def serialize(resp: QueryResponse) -> dict:
    body = asdict(resp)
    for path, rendered in zip(body["retrieval"]["paths"], resp.retrieval.paths):
        path["rendered"] = rendered.render()
    return body


@router.post("/query")
def query(req: QueryRequest, svc: Services = Depends(services)):
    try:
        resp = svc.query.run(req.question.strip(), req.mode, req.overrides)
    except ValueError as exc:  # includes pydantic ValidationError from invalid overrides
        raise ApiError(400, "invalid_overrides", str(exc)) from exc
    return serialize(resp)
