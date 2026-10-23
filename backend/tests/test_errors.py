from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def failing_route() -> Generator[str, None, None]:
    """Ajoute temporairement une route qui plante, retirée après le test."""
    path = "/__test-erreur-500"

    async def boom():
        raise RuntimeError("panne simulée")

    app.add_api_route(path, boom)
    yield path
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != path]


def test_unhandled_error_returns_json_500_with_cors_headers(client: TestClient, failing_route: str):
    response = client.get(failing_route, headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Erreur interne du serveur"}
    # Sans ce header, le navigateur masquerait le 500 derrière une « erreur réseau »
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
