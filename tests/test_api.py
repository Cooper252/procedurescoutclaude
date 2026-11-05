from fastapi.testclient import TestClient

from procedurescout_api.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version() -> None:
    response = client.get("/v1/meta/version")
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"


def test_unknown_route_is_404() -> None:
    assert client.get("/v1/compare").status_code == 404
