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
    assert payload["mp_preference_id"] is None
    assert payload["payment_provider"] is None
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


def test_create_payment_preference_with_valid_order(client):
    order_response = client.post(
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
        },
    )
    order_id = order_response.json()["id"]

    response = client.post("/api/v1/payments/create-preference", json={"order_id": order_id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == order_id
    assert payload["preference_id"] == "pref_test_123"
    assert payload["sandbox_init_point"] == "https://mp.test/sandbox"


def test_create_payment_preference_from_cart_does_not_create_order(client):
    response = client.post(
        "/api/v1/payments/create-preference",
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
            "customer_data": {"name": "Invitado"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] is None
    assert payload["checkout_session_id"] == 1
    assert payload["external_reference"]

    order = client.get("/api/v1/orders/1")
    assert order.status_code == 404


def test_webhook_approved_creates_order_once_from_checkout_session(client):
    preference = client.post(
        "/api/v1/payments/create-preference",
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
        },
    )
    assert preference.status_code == 200

    first = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_checkout_1"}},
    )
    second = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_checkout_1"}},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    order = client.get("/api/v1/orders/1")
    assert order.status_code == 200
    payload = order.json()
    assert payload["payment_status"] == "pagado"
    assert payload["mp_payment_id"] == "pay_approved_checkout_1"

    missing_second_order = client.get("/api/v1/orders/2")
    assert missing_second_order.status_code == 404


def test_webhook_rejected_saves_payment_without_creating_order(client):
    preference = client.post(
        "/api/v1/payments/create-preference",
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
        },
    )
    assert preference.status_code == 200

    response = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_rejected_checkout_1"}},
    )

    assert response.status_code == 200
    order = client.get("/api/v1/orders/1")
    assert order.status_code == 404


def test_webhook_duplicate_does_not_duplicate_order(client):
    preference = client.post(
        "/api/v1/payments/create-preference",
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
        },
    )
    assert preference.status_code == 200

    for _ in range(2):
        response = client.post(
            "/api/v1/payments/webhook",
            json={"type": "payment", "data": {"id": "pay_approved_duplicate_1"}},
        )
        assert response.status_code == 200

    assert client.get("/api/v1/orders/1").status_code == 200
    assert client.get("/api/v1/orders/2").status_code == 404


def test_debug_preference_payload_available_in_debug(client, monkeypatch):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "debug", True)
    order_response = client.post(
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
        },
    )
    order_id = order_response.json()["id"]

    response = client.post("/api/v1/payments/debug/preference-payload", json={"order_id": order_id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["external_reference"] == str(order_id)
    assert payload["notification_url"].startswith("https://")
    assert payload["items"][0]["currency_id"] == "CLP"
    assert payload["payer"]["email"] == "guest@yakero.cl"


def test_debug_preference_payload_without_email_omits_payer(client, monkeypatch, auth_header):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "debug", True)
    order_response = client.post(
        "/api/v1/orders/",
        headers=auth_header,
        json={
            "delivery_type": "retiro",
            "items": [
                {
                    "product_id": 1,
                    "quantity": 1,
                    "selected_modifiers": [{"modifier_option_id": 1}],
                }
            ],
        },
    )
    order_id = order_response.json()["id"]

    response = client.post(
        "/api/v1/payments/debug/preference-payload",
        headers=auth_header,
        json={"order_id": order_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "payer" not in payload


def test_create_order_does_not_call_mercado_pago(client, monkeypatch):
    from app.infrastructure.api.routers import orders as orders_router_module

    class FailingMercadoPagoService:
        def __init__(self, *args, **kwargs):
            raise AssertionError("orders endpoint should not instantiate Mercado Pago")

    monkeypatch.setattr(orders_router_module, "MercadoPagoService", FailingMercadoPagoService, raising=False)

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
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["mp_preference_id"] is None


def test_payment_preference_failure_does_not_break_order_creation(client, monkeypatch):
    from app.infrastructure.api.routers import payments as payments_router_module
    from app.infrastructure.api import errors as api_errors_module
    from app.domain.exceptions import PaymentError

    order_response = client.post(
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
        },
    )
    assert order_response.status_code == 201
    order_id = order_response.json()["id"]

    class FailingMercadoPagoService:
        async def create_preference(self, _order, back_urls):
            raise PaymentError(
                "Mercado Pago rechazo la solicitud. Revisa configuracion, credenciales TEST y URLs publicas.",
                status_code=400,
                debug_detail={
                    "provider": "mercadopago",
                    "provider_status_code": 400,
                    "provider_response": {"message": "invalid notification_url"},
                    "request_payload": {"notification_url": "http://127.0.0.1:8000/api/v1/payments/webhook"},
                },
            )

        async def get_payment(self, payment_id: str):
            return None

    monkeypatch.setattr(payments_router_module, "MercadoPagoService", FailingMercadoPagoService)
    monkeypatch.setattr(api_errors_module.settings, "debug", True)

    response = client.post("/api/v1/payments/create-preference", json={"order_id": order_id})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PAYMENT_ERROR"
    assert response.json()["detail"]["debug"]["provider_status_code"] == 400
    assert "notification_url" in response.json()["detail"]["debug"]["request_payload"]

    order = client.get(f"/api/v1/orders/{order_id}")
    payload = order.json()
    assert payload["id"] == order_id
    assert payload["mp_preference_id"] is None


def test_reject_payment_preference_for_missing_order(client):
    response = client.post("/api/v1/payments/create-preference", json={"order_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_reject_payment_preference_for_paid_order(client):
    order_response = client.post(
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
        },
    )
    order_id = order_response.json()["id"]

    webhook_response = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_1"}},
    )
    assert webhook_response.status_code == 200

    response = client.post("/api/v1/payments/create-preference", json={"order_id": order_id})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_webhook_payment_approved_updates_order(client):
    order_response = client.post(
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
        },
    )
    order_id = order_response.json()["id"]

    response = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_1"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    order = client.get(f"/api/v1/orders/{order_id}")
    payload = order.json()
    assert payload["payment_status"] == "pagado"
    assert payload["mp_payment_id"] == "pay_approved_1"


def test_get_order_exposes_payment_status(client):
    order_response = client.post(
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
        },
    )
    order_id = order_response.json()["id"]
    response = client.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["payment_status"] == "pendiente"


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


def test_internal_bootstrap_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module.settings, "environment", "staging")

    response = client.post("/api/v1/internal/bootstrap")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token interno invalido."


def test_internal_bootstrap_is_idempotent(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    state = {"calls": 0}

    async def fake_run_alembic_upgrade():
        return None

    async def fake_run_seed_and_collect():
        state["calls"] += 1
        if state["calls"] == 1:
            return {
                "created": {
                    "categories": 8,
                    "products": 8,
                    "demo_user": True,
                    "demo_coupon": True,
                },
                "existing": {
                    "categories": 0,
                    "products": 0,
                    "demo_user": False,
                    "demo_coupon": False,
                },
            }
        return {
            "created": {
                "categories": 0,
                "products": 0,
                "demo_user": False,
                "demo_coupon": False,
            },
            "existing": {
                "categories": 8,
                "products": 8,
                "demo_user": True,
                "demo_coupon": True,
            },
        }

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module.settings, "environment", "staging")
    monkeypatch.setattr(internal_router_module.settings, "debug", False)
    monkeypatch.setattr(internal_router_module, "_run_alembic_upgrade", fake_run_alembic_upgrade)
    monkeypatch.setattr(internal_router_module, "_run_seed_and_collect", fake_run_seed_and_collect)

    first = client.post("/api/v1/internal/bootstrap", headers={"X-Internal-Token": "secret-token"})
    second = client.post("/api/v1/internal/bootstrap", headers={"X-Internal-Token": "secret-token"})

    assert first.status_code == 200
    assert first.json()["migrations"] == "ok"
    assert first.json()["seed"] == "ok"
    assert first.json()["created"]["products"] == 8

    assert second.status_code == 200
    assert second.json()["created"]["products"] == 0
    assert second.json()["existing"]["products"] == 8
