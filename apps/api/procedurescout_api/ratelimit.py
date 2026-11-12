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
import ipaddress
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
    ("/v1/email-prices", ("POST",), 10, 3600),
    ("/v1/portal/mfa/verify", ("POST",), 20, 600),
    ("/v1/stripe/webhook", ("POST",), 600, 60),
    ("/v1/events", ("POST",), 120, 60),
    ("/", ("POST", "PUT", "DELETE"), 60, 60),
    ("/", ("GET",), 300, 60),
)
_counts: dict[tuple[str, str, int], int] = {}
_last_sweep = 0.0


_INTERNAL = tuple(
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _public(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not any(a.version == n.version and a in n for n in _INTERNAL)


def public_ip(request: Request) -> str | None:
    """The right-most public address in the forwarding chain (see _client)."""
    chain = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",")]
    chain.append(request.client.host if request.client else "")
    return next((x for x in reversed(chain) if _public(x)), None)


def _client(request: Request) -> str | None:
    """The visitor, or None for the website's own server.

    X-Forwarded-For is a chain that each proxy appends to, so the first entry
    can be typed by anyone; the right-most *public* address is the one Render
    saw (2026-11-12). Requests with no public address come from inside the
    hosting network: the website rendering pages for crawlers and visitors. Those
    are not limited here (they would all share one limit and pages would show
    "no prices"); the pages themselves are cached for hours."""
    chain = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",")]
    chain.append(request.client.host if request.client else "")
    ip = next((x for x in reversed(chain) if _public(x)), None)
    if ip is None:
        return None
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
            who = _client(request)
            if who is None:
                return None
            bucket = int(t // window)
            key = (prefix + method, who, bucket)
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
