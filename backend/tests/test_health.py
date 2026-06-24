"""Smoke test: the app boots and the health endpoint responds.

M0 has no numerics yet; this just proves the FastAPI app is wired correctly.
The reference-validated pricing tests arrive with M1.
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
