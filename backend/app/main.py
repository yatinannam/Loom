"""FastAPI application. Run with `uv run uvicorn app.main:app --reload`."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, graph, query, system
from app.api.errors import install_error_handlers
from app.config import get_settings
from app.logging import configure_logging
from app.services import Services, build_services


def create_app(services: Services | None = None) -> FastAPI:
    settings = services.settings if services else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if services is None:
            configure_logging()
            app.state.services = build_services(settings)
        else:
            app.state.services = services
        yield

    app = FastAPI(title="Loom GraphRAG API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for router in (system.router, documents.router, graph.router, query.router):
        app.include_router(router)
    return app


app = create_app()
