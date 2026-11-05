"""FastAPI application. Phase 0 exposes only health and version endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from procedurescout_core import __version__ as core_version

API_VERSION = "v1"

app = FastAPI(
    title="ProcedureScout API",
    version=core_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
)


class Health(BaseModel):
    status: str


class VersionInfo(BaseModel):
    api_version: str
    app_version: str


@app.get("/healthz", response_model=Health, tags=["meta"])
def healthz() -> Health:
    """Liveness check. Does not touch the database."""
    return Health(status="ok")


@app.get(f"/{API_VERSION}/meta/version", response_model=VersionInfo, tags=["meta"])
def version() -> VersionInfo:
    return VersionInfo(api_version=API_VERSION, app_version=core_version)
