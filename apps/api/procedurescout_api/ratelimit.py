"""Simple per-visitor rate limits (launch requirement).

Counts requests per visitor in memory only (a keyed hash of the address, never
stored or logged) in fixed one-minute or ten-minute windows. Limits are
generous for people and stop scripts from flooding sign-in, review emails,
counts or searches. One API instance at launch, so in-memory is enough; a
shared store is needed only if more instances are added.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_KEY = secrets.token_bytes(16)  # per process; hashes can't be reversed or linked later
# (path prefix, methods, max requests, window seconds); first match wins
RULES: tuple[tuple[str, tuple[str, ...], int, int], ...] = (
    ("/v1/portal/sign-in", ("POST",), 10, 600),
    ("/v1/reviews/request", ("POST",), 10, 600),
    ("/v1/price-reports", ("POST",), 20, 600),
    ("/v1/portal/mfa/verify", ("POST",), 20, 600),
    ("/v1/stripe/webhook", ("POST",), 600, 60),
    ("/v1/events", ("POST",), 120, 60),
    ("/", ("POST", "PUT", "DELETE"), 60, 60),
    ("/", ("GET",), 300, 60),
)
_counts: dict[tuple[str, str, int], int] = {}
_last_sweep = 0.0


def _client(request: Request) -> str:
    # Render (and the website proxy) put the visitor's address first in X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
    return hmac.new(_KEY, ip.encode(), hashlib.sha256).hexdigest()[:24]


def check(request: Request, now: float | None = None) -> int | None:
    """Seconds to wait if this request is over its limit, else None."""
    global _last_sweep
    t = time.time() if now is None else now
    path, method = request.url.path, request.method
    if path == "/healthz":
        return None
    for prefix, methods, limit, window in RULES:
        if path.startswith(prefix) and method in methods:
            bucket = int(t // window)
            key = (prefix + method, _client(request), bucket)
            _counts[key] = _counts.get(key, 0) + 1
            if t - _last_sweep > 60:  # forget old windows
                _last_sweep = t
                for k in [k for k in _counts if k[2] < int(t // 600) - 1 and k[2] < bucket - 1]:
                    _counts.pop(k, None)
            if _counts[key] > limit:
                return int((bucket + 1) * window - t) + 1
            return None
    return None


async def middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    wait = check(request)
    if wait is not None:
        return JSONResponse(
            {"detail": "Too many requests. Please wait a moment and try again."},
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    return await call_next(request)


def reset() -> None:
    """For tests."""
    _counts.clear()
