"""Per-visitor rate limits (launch requirement)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from procedurescout_api import ratelimit
from procedurescout_api.main import app


def test_sign_in_is_limited_per_visitor_and_health_is_not() -> None:
    ratelimit.reset()
    c = TestClient(app)
    h = {"X-ProcedureScout": "1", "X-Forwarded-For": "203.0.113.7"}
    codes = [
        c.post("/v1/portal/sign-in", json={"email": "a@b.test"}, headers=h).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429 and 429 not in codes[:10]
    other = {"X-ProcedureScout": "1", "X-Forwarded-For": "198.51.100.9"}
    assert (
        c.post("/v1/portal/sign-in", json={"email": "a@b.test"}, headers=other).status_code != 429
    )
    assert all(c.get("/healthz").status_code == 200 for _ in range(400))
    ratelimit.reset()
