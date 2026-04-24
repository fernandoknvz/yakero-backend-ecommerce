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


def test_demo_user_can_login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "feradmin@example.com", "password": "Admin123456"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == 2
    assert payload["role"] == "admin"


def test_list_categories(client):
    response = client.get("/api/v1/categories/")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["slug"] == "rolls"


def test_list_products(client):
    response = client.get("/api/v1/products/")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["category"]["slug"] == "rolls"
    assert payload[0]["flags"]["is_configurable"] is True


def test_get_product_detail(client):
    response = client.get("/api/v1/products/1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "yakero-roll"
    assert payload["category"]["slug"] == "rolls"
    assert len(payload["modifier_groups"]) == 2
    assert len(payload["applicable_promotions"]) == 1


def test_filter_products_by_category(client):
    response = client.get("/api/v1/products/?category_slug=bebidas")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["slug"] == "limonada"


def test_create_valid_preview(client):
    response = client.post(
        "/api/v1/orders/preview",
        json={
            "delivery_type": "retiro",
            "guest_email": "guest@yakero.cl",
            "items": [
                {
                    "product_id": 1,
                    "quantity": 2,
                    "selected_modifiers": [
                        {"modifier_option_id": 1},
                        {"modifier_option_id": 2},
                    ],
                }
            ],
            "coupon_code": "SAVE10",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["subtotal"] == "11480"
    assert payload["discount"] == "1148"
    assert payload["total"] == "10332"
    assert payload["pricing"]["coupon_discount"] == "1148"


def test_reject_invalid_configuration_preview(client):
    response = client.post(
        "/api/v1/orders/preview",
        json={
            "delivery_type": "retiro",
            "guest_email": "guest@yakero.cl",
            "items": [{"product_id": 1, "quantity": 1}],
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["code"] == "MODIFIER_REQUIRED"


def test_create_valid_order(client):
    response = client.post(
        "/api/v1/orders/",
        json={
            "delivery_type": "retiro",
            "guest_email": "guest@yakero.cl",
            "items": [
                {
                    "product_id": 1,
                    "quantity": 1,
                    "selected_modifiers": [{"modifier_option_id": 1}],
                }
            ],
            "notes": "sin wasabi",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["mp_preference_id"] == "pref_test_123"
    assert payload["total"] == "5490"


def test_reject_order_with_manipulated_total(client):
    response = client.post(
        "/api/v1/orders/",
        json={
            "delivery_type": "retiro",
            "guest_email": "guest@yakero.cl",
            "items": [
                {
                    "product_id": 1,
                    "quantity": 1,
                    "selected_modifiers": [{"modifier_option_id": 1}],
                }
            ],
            "client_totals": {
                "total": "1000",
            },
        },
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["code"] == "ORDER_PRICING_MISMATCH"


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
