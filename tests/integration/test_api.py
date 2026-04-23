def test_healthcheck(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_register_and_me(client):
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new-user@yakero.cl",
            "password": "supersecreto123",
            "first_name": "New",
            "last_name": "User",
            "phone": "+56922223333",
        },
    )
    assert register_response.status_code == 201
    payload = register_response.json()
    assert payload["token_type"] == "bearer"

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "new-user@yakero.cl"


def test_auth_me_requires_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token requerido."


def test_create_guest_order(client):
    response = client.post(
        "/api/v1/orders/",
        json={
            "delivery_type": "retiro",
            "guest_email": "guest@yakero.cl",
            "items": [{"product_id": 1, "quantity": 2}],
            "notes": "sin wasabi",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["mp_preference_id"] == "pref_test_123"
    assert payload["total"] == "9980"


def test_validate_coupon(client):
    response = client.post(
        "/api/v1/coupons/validate",
        json={"code": "SAVE10", "order_subtotal": "5000"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "SAVE10"
    assert payload["calculated_discount"] == "500"


def test_webhook_invalid_signature(client, monkeypatch):
    from app.infrastructure.api.routers import webhooks as webhooks_router_module

    monkeypatch.setattr(webhooks_router_module.settings, "mp_webhook_secret", "secret")
    response = client.post(
        "/webhooks/mercadopago",
        headers={"x-signature": "bad-signature"},
        json={"type": "payment", "data": {"id": 123}},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Firma de webhook invalida"
