"""FastAPI application: health/version, public search (search_routes) and the
review page (admin_routes, off unless configured)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from procedurescout_core import __version__ as core_version

from .admin_portal_routes import router as admin_portal_router
from .admin_routes import router as admin_router
from .analytics_routes import router as analytics_router
from .care_routes import router as care_router
from .email_routes import router as email_router
from .portal_routes import router as portal_router
from .portal_routes import send_mail_soon
from .search_routes import router as search_router

API_VERSION = "v1"
MAIL_RETRY_SECONDS = 300


async def _retry_mail_forever() -> None:
    """Every 5 minutes, send any email still waiting (a sign-in link whose first
    try failed, or one queued while the email key wasn't set). Never raises."""
    while True:
        await asyncio.sleep(MAIL_RETRY_SECONDS)
        await asyncio.to_thread(send_mail_soon)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_retry_mail_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
    title="ProcedureScout API",
    version=core_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

from .ratelimit import middleware as rate_limit  # noqa: E402


@app.exception_handler(StarletteHTTPException)
async def _review_pages_in_a_browser(request: Request, exc: StarletteHTTPException) -> Response:
    """Someone opening a review page in a browser without being signed in goes
    to the sign-in page instead of seeing a line of JSON (go-live check,
    2026-11-12). Everything else keeps the normal JSON errors."""
    browser = request.method == "GET" and "text/html" in request.headers.get("accept", "")
    if browser and request.url.path.startswith("/admin"):
        if exc.status_code == 401:
            return RedirectResponse("/providers/account", status_code=303)
        if exc.status_code == 403:
            return HTMLResponse(
                "<!doctype html><title>ProcedureScout review</title>"
                "<p>This account can't use the review pages. "
                '<a href="/providers/account">Back to your account</a></p>',
                status_code=403,
            )
    return await http_exception_handler(request, exc)


app.middleware("http")(rate_limit)
app.include_router(search_router)
app.include_router(care_router)
app.include_router(email_router)
app.include_router(portal_router)
app.include_router(admin_router)
app.include_router(analytics_router)
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
