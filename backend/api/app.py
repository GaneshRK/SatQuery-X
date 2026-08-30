"""SatQuery-X FastAPI Application Factory."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import auth, health, images, models, queries, reports, sessions
from backend.config import get_settings
from backend.logging_config import configure_logging
from backend.storage.s3 import ObjectStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Initialize storage directories
    storage = ObjectStorage()
    storage.ensure_bucket()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SatQuery-X API",
        description="Agentic Geospatial Intelligence Engine for Multimodal Satellite Reasoning (SIH26167)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include Versioned Routers (/v1/...)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(images.router)
    app.include_router(queries.router)
    app.include_router(reports.router)
    app.include_router(models.router)

    # Also support /api/v1 prefix for proxy configurations
    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(sessions.router, prefix=api_prefix)
    app.include_router(images.router, prefix=api_prefix)
    app.include_router(queries.router, prefix=api_prefix)
    app.include_router(reports.router, prefix=api_prefix)
    app.include_router(models.router, prefix=api_prefix)

    # Storage direct file serving fallback endpoint
    @app.get("/api/v1/storage/{file_path:path}")
    @app.get("/v1/storage/{file_path:path}")
    async def serve_storage_file(file_path: str):
        local_file = Path("data/storage") / file_path
        if local_file.exists() and local_file.is_file():
            # Determine content type
            ext = local_file.suffix.lower()
            media_type = "image/png" if ext == ".png" else "text/html" if ext in {".html", ".htm"} else "application/octet-stream"
            return FileResponse(local_file, media_type=media_type)
        raise HTTPException(status_code=404, detail="File not found in storage.")

    return app


app = create_app()
