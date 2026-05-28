from fastapi.testclient import TestClient

from app.main import app


def test_cors_preflight_allows_deployed_frontend_origin():
    client = TestClient(app)

    response = client.options(
        "/api/v1/products/",
        headers={
            "Origin": "https://ecommerce.fernandoolgueadev.cl",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://ecommerce.fernandoolgueadev.cl"
    assert response.headers["access-control-allow-credentials"] == "true"
