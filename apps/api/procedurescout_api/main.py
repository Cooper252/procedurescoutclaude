"""FastAPI application: health/version, public search (search_routes) and the
review page (admin_routes, off unless configured)."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from procedurescout_core import __version__ as core_version

from .admin_portal_routes import router as admin_portal_router
from .admin_routes import router as admin_router
from .care_routes import router as care_router
from .portal_routes import router as portal_router
from .search_routes import router as search_router

API_VERSION = "v1"

app = FastAPI(
    title="ProcedureScout API",
    version=core_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

from .ratelimit import middleware as rate_limit  # noqa: E402

app.middleware("http")(rate_limit)
app.include_router(search_router)
app.include_router(care_router)
app.include_router(portal_router)
app.include_router(admin_router)
app.include_router(admin_portal_router)


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
