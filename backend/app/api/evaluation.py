from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import require_ingest_ready, services
from app.api.errors import ApiError
from app.services import Services

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class RunRequest(BaseModel):
    modes: list[str] = Field(default_factory=lambda: ["standard", "graph", "hybrid"], min_length=1)


def _run(svc: Services, run_id: str) -> dict:
    run = svc.registry.get_eval_run(run_id)
    if run is None:
        raise ApiError(404, "not_found", f"evaluation run {run_id} not found")
    return {**run, "progress": svc.evaluation.progress(run_id)}


@router.post("/load-corpus")
def load_corpus(svc: Services = Depends(services)):
    require_ingest_ready(svc)
    ids = svc.evaluation.load_corpus()
    return {"document_ids": ids, "documents": [svc.registry.get_document(i) for i in ids]}


@router.post("/run", status_code=202)
def run(req: RunRequest, svc: Services = Depends(services)):
    try:
        run_id = svc.evaluation.start(req.modes)
    except ValueError as exc:
        raise ApiError(400, "invalid_modes", str(exc)) from exc
    except RuntimeError as exc:
        raise ApiError(409, "run_in_progress", str(exc)) from exc
    return _run(svc, run_id)


@router.get("/runs")
def runs(svc: Services = Depends(services)):
    return svc.registry.list_eval_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str, svc: Services = Depends(services)):
    return _run(svc, run_id)


@router.get("/runs/{run_id}/results")
def run_results(run_id: str, svc: Services = Depends(services)):
    _run(svc, run_id)
    return [r["record"] for r in svc.registry.eval_results(run_id)]


@router.get("/results")
def latest_results(svc: Services = Depends(services)):
    run = svc.registry.latest_eval_run()
    if run is None:
        raise ApiError(404, "not_found", "no evaluation run yet")
    return {"run": _run(svc, run["id"]), "results": [r["record"] for r in svc.registry.eval_results(run["id"])]}


@router.get("/runs/{run_id}/export")
def export(run_id: str, format: str = Query("json", pattern="^(json|csv)$"), svc: Services = Depends(services)):
    _run(svc, run_id)
    content, media = svc.evaluation.export(run_id, format)
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="loom-eval-{run_id}.{format}"'})
