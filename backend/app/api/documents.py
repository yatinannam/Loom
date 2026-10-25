from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile

from app.api.deps import require_ingest_ready, services
from app.api.errors import ApiError
from app.ingestion.parsing import validate_upload
from app.registry import DocumentRow
from app.services import Services

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get(svc: Services, document_id: str) -> DocumentRow:
    doc = svc.registry.get_document(document_id)
    if doc is None:
        raise ApiError(404, "not_found", f"document {document_id} not found")
    return doc


@router.post("/upload", status_code=201, response_model=list[DocumentRow])
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...),
                 svc: Services = Depends(services)):
    require_ingest_ready(svc)
    limit = svc.settings.max_upload_mb * 1024 * 1024
    uploads = []
    for f in files:
        data = await f.read(limit + 1)  # one byte over the limit is enough to reject
        name = f.filename or "upload"
        validate_upload(name, data, limit)  # all files are checked before any is stored
        uploads.append((name, data))
    rows = [svc.ingestion.add_file(name, data) for name, data in uploads]
    for row in rows:
        background.add_task(svc.ingestion.ingest, row.id)
    return rows


@router.get("", response_model=list[DocumentRow])
def list_documents(svc: Services = Depends(services)):
    return svc.registry.list_documents()


@router.get("/{document_id}", response_model=DocumentRow)
def get_document(document_id: str, svc: Services = Depends(services)):
    return _get(svc, document_id)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, svc: Services = Depends(services)):
    _get(svc, document_id)
    svc.graph.get()
    svc.ingestion.remove(document_id)
    return Response(status_code=204)


@router.post("/{document_id}/ingest", status_code=202, response_model=DocumentRow)
def reingest(document_id: str, background: BackgroundTasks, svc: Services = Depends(services)):
    doc = _get(svc, document_id)
    require_ingest_ready(svc)
    background.add_task(svc.ingestion.ingest, document_id)
    return doc


@router.get("/{document_id}/chunks")
def chunks(document_id: str, svc: Services = Depends(services)):
    _get(svc, document_id)
    return svc.vector.chunks_for_document(document_id)


@router.get("/{document_id}/errors")
def errors(document_id: str, svc: Services = Depends(services)):
    _get(svc, document_id)
    return svc.registry.list_extraction_errors(document_id)
