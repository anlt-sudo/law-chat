"""FastAPI app – `uvicorn app.main:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import request_id_middleware, setup_logging
from app.db.es import close_es
from app.db.neo4j import close_driver
from app.db.neo4j_schema import ensure_schema
from app.db.pg import dispose_engine

logger = logging.getLogger("app")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        await ensure_schema()
    except Exception:
        # Không chặn khởi động: /health sẽ báo Neo4j lỗi, lần khởi động sau tạo lại
        logger.exception("Không tạo được Neo4j schema lúc khởi động")
    yield
    await dispose_engine()
    await close_driver()
    await close_es()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="LegalGraph API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    # Module sau thêm router tại đây
    app.include_router(api)
    return app


app = create_app()
