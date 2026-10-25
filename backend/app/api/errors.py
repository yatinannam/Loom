"""Uniform error responses: {"error": {"code", "message"}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.graph.store import GraphUnavailable
from app.ingestion.parsing import UploadRejected
from app.llm.provider import LLMBadResponse, LLMError, LLMNotConfigured, LLMRateLimited

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def error_response(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def _llm_status(exc: LLMError) -> int:
    if isinstance(exc, LLMNotConfigured):
        return 503
    if isinstance(exc, LLMRateLimited):
        return 429
    if isinstance(exc, LLMBadResponse):
        return 502
    return 503


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, str(exc))

    @app.exception_handler(UploadRejected)
    async def upload_rejected(_: Request, exc: UploadRejected):
        return error_response(400, exc.code, str(exc))

    @app.exception_handler(GraphUnavailable)
    async def graph_unavailable(_: Request, exc: GraphUnavailable):
        return error_response(503, exc.code, str(exc))

    @app.exception_handler(LLMError)
    async def llm_error(_: Request, exc: LLMError):
        return error_response(_llm_status(exc), exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return error_response(422, "validation_error", "request validation failed", details=details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return error_response(500, "internal_error", "internal server error")
