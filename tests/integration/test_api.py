import httpx


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
    assert payload[0]["subcategory"] == "Hand Rolls"
    assert payload[0]["flags"]["is_configurable"] is True


def test_get_product_detail(client):
    response = client.get("/api/v1/products/1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "yakero-roll"
    assert payload["category"]["slug"] == "rolls"
    assert payload["subcategory"] == "Hand Rolls"
    assert len(payload["modifier_groups"]) == 2
    assert len(payload["applicable_promotions"]) == 1


def test_filter_products_by_category(client):
    response = client.get("/api/v1/products/?category_slug=bebidas")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["slug"] == "limonada"
    assert payload[0]["subcategory"] is None


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


def test_public_create_order_is_blocked(client):
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
    assert response.status_code == 401
    assert client.get("/api/v1/orders/1").status_code == 404


def test_reject_order_with_manipulated_total(client):
    response = client.post(
        "/api/v1/orders/preview",
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


def test_create_payment_preference_with_valid_order(client, admin_header):
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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
        "/api/v1/payments/create-preference",
        headers=admin_header,
        json={"order_id": order_id},
    )
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


def test_payment_status_pending_is_public_for_guest(client):
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
    external_reference = preference.json()["external_reference"]

    response = client.get(f"/api/v1/payments/status/{external_reference}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["external_reference"] == external_reference
    assert payload["checkout_session_status"] == "pending"
    assert payload["payment_status"] is None
    assert payload["order_id"] is None
    assert payload["total"] == "5490"


def test_payment_status_approved_exposes_order_without_login(client):
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
    external_reference = preference.json()["external_reference"]
    webhook = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_status_1"}},
    )
    assert webhook.status_code == 200

    response = client.get(f"/api/v1/payments/status/{external_reference}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checkout_session_status"] == "paid"
    assert payload["payment_status"] == "approved"
    assert payload["order_id"] == 1
    assert payload["order_status"] == "confirmed"


def test_payment_status_amount_mismatch_is_public_without_order(client):
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
    external_reference = preference.json()["external_reference"]
    client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": "pay_approved_mismatch_status_1"}},
    )

    response = client.get(f"/api/v1/payments/status/{external_reference}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checkout_session_status"] == "amount_mismatch"
    assert payload["payment_status"] == "amount_mismatch"
    assert payload["order_id"] is None


def test_payment_status_not_found_is_controlled(client):
    response = client.get("/api/v1/payments/status/not-real-reference")

    assert response.status_code == 404
    assert response.json()["detail"] == "Checkout no encontrado."


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


def test_webhook_amount_mismatch_does_not_create_order(client):
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
        json={"type": "payment", "data": {"id": "pay_approved_mismatch_1"}},
    )

    assert response.status_code == 200
    assert client.get("/api/v1/orders/1").status_code == 404


def test_webhook_duplicate_does_not_duplicate_order(client):
    from tests.conftest import FakePaymentRepository

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
    assert len(FakePaymentRepository.payments) == 1


def test_debug_preference_payload_available_in_debug(client, monkeypatch, admin_header):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "debug", True)
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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
        "/api/v1/payments/debug/preference-payload",
        headers=admin_header,
        json={"order_id": order_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["external_reference"] == str(order_id)
    assert payload["notification_url"].startswith("https://")
    assert payload["items"][0]["currency_id"] == "CLP"


def test_debug_mercadopago_config_is_internal_and_masks_token(client, monkeypatch):
    from app.infrastructure.api.routers import debug as debug_router_module

    monkeypatch.setattr(debug_router_module.settings, "internal_bootstrap_token", "internal-secret")
    monkeypatch.setattr(debug_router_module.settings, "mp_access_token", "APP_USR-super-secret-token")
    monkeypatch.setattr(debug_router_module.settings, "mp_env", "production")
    monkeypatch.setattr(debug_router_module.settings, "backend_public_url", "https://api.yakero.cl")
    monkeypatch.setattr(debug_router_module.settings, "frontend_public_url", "https://yakero.cl")

    unauthorized = client.get("/api/v1/debug/mercadopago")
    assert unauthorized.status_code == 401

    response = client.get(
        "/api/v1/debug/mercadopago",
        headers={"X-Internal-Token": "internal-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mp_token_exists"] is True
    assert payload["mp_token_prefix"] == "APP_USR"
    assert payload["mp_token_length"] == len("APP_USR-super-secret-token")
    assert "super-secret-token" not in str(payload)
    assert payload["frontend_url"] == "https://yakero.cl"
    assert payload["backend_url"] == "https://api.yakero.cl"
    assert payload["notification_url"] == "https://api.yakero.cl/api/v1/payments/webhook"
    assert payload["success_url"].startswith("https://yakero.cl/checkout/success")
    assert payload["currency_id"] == "CLP"
    assert payload["environment"] == "production"
    assert payload["usa_sandbox_init_point"] is False


def test_debug_pos_catalog_summary_uses_pos_client(client, monkeypatch):
    from app.infrastructure.api.routers import debug as debug_router_module

    class FakePosClient:
        base_url = "https://posdev.tehagolaweb.cl"

        async def get_catalog_summary(self):
            return {"products": 12, "promotions": 3, "branches": 2}

    monkeypatch.setattr(debug_router_module.settings, "internal_bootstrap_token", "internal-secret")
    monkeypatch.setattr(debug_router_module, "PosClient", FakePosClient)

    response = client.get(
        "/api/v1/debug/pos/catalog-summary",
        headers={"X-Internal-Token": "internal-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["source"] == "pos"
    assert payload["base_url"] == "https://posdev.tehagolaweb.cl"
    assert payload["summary"] == {"products": 12, "promotions": 3, "branches": 2}


def test_debug_pos_config_is_internal_and_masks_token(client, monkeypatch):
    from app.infrastructure.api.routers import debug as debug_router_module

    monkeypatch.setattr(debug_router_module.settings, "internal_bootstrap_token", "internal-secret")
    monkeypatch.setattr(debug_router_module.settings, "pos_api_base_url", "https://pos.test")
    monkeypatch.setattr(debug_router_module.settings, "pos_internal_token", "pos-token-super-secret")

    unauthorized = client.get("/api/v1/debug/config/pos")
    assert unauthorized.status_code == 401

    response = client.get(
        "/api/v1/debug/config/pos",
        headers={"X-Internal-Token": "internal-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["POS_API_BASE_URL"] == "https://pos.test"
    assert payload["pos_internal_token_configured"] is True
    assert payload["pos_internal_token_length"] == len("pos-token-super-secret")
    assert payload["pos_internal_token_preview"] == "pos-...cret"
    assert payload["internal_bootstrap_token_configured"] is True
    assert payload["internal_bootstrap_token_length"] == len("internal-secret")
    assert "pos-token-super-secret" not in str(payload)
    assert "internal-secret" not in str(payload)


def test_debug_pos_raw_summary_uses_direct_httpx_and_masks_token(client, monkeypatch):
    from app.infrastructure.api.routers import debug as debug_router_module

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://posdev.tehagolaweb.cl/api/external/catalog/summary"
        assert request.headers["X-Internal-Token"] == "pos-token-super-secret"
        return httpx.Response(403, text="forbidden detail from pos")

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(debug_router_module.settings, "internal_bootstrap_token", "internal-secret")
    monkeypatch.setattr(debug_router_module.settings, "pos_internal_token", "pos-token-super-secret")
    monkeypatch.setattr(debug_router_module.httpx, "AsyncClient", fake_async_client)

    response = client.get(
        "/api/v1/debug/pos/raw-summary",
        headers={"X-Internal-Token": "internal-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status_code"] == 403
    assert payload["response_text_preview"] == "forbidden detail from pos"
    assert payload["request_url"] == "https://posdev.tehagolaweb.cl/api/external/catalog/summary"
    assert payload["token_length"] == len("pos-token-super-secret")
    assert payload["token_preview"] == "pos-...cret"
    assert "pos-token-super-secret" not in str(payload)


def test_debug_preference_payload_without_email_omits_payer(client, monkeypatch, admin_header):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "debug", True)
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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
        headers=admin_header,
        json={"order_id": order_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "payer" not in payload


def test_debug_checkout_payload_includes_external_reference_in_back_urls(client, monkeypatch):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "debug", True)
    response = client.post(
        "/api/v1/payments/debug/preference-payload",
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

    assert response.status_code == 200
    payload = response.json()
    assert "external_reference=debug_checkout_session" in payload["back_urls"]["success"]


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

    assert response.status_code == 401


def test_payment_preference_failure_does_not_break_order_creation(client, monkeypatch, admin_header):
    from app.infrastructure.api.routers import payments as payments_router_module
    from app.infrastructure.api import errors as api_errors_module
    from app.domain.exceptions import PaymentError

    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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

    response = client.post(
        "/api/v1/payments/create-preference",
        headers=admin_header,
        json={"order_id": order_id},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PAYMENT_ERROR"
    assert response.json()["detail"]["debug"]["provider_status_code"] == 400
    assert "notification_url" in response.json()["detail"]["debug"]["request_payload"]

    order = client.get(f"/api/v1/orders/{order_id}", headers=admin_header)
    payload = order.json()
    assert payload["id"] == order_id
    assert payload["mp_preference_id"] is None


def test_reject_payment_preference_for_missing_order(client):
    response = client.post("/api/v1/payments/create-preference", json={"order_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_reject_payment_preference_for_paid_order(client, admin_header):
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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

    response = client.post(
        "/api/v1/payments/create-preference",
        headers=admin_header,
        json={"order_id": order_id},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_webhook_payment_approved_updates_order(client, admin_header):
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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

    order = client.get(f"/api/v1/orders/{order_id}", headers=admin_header)
    payload = order.json()
    assert payload["payment_status"] == "pagado"
    assert payload["mp_payment_id"] == "pay_approved_1"


def test_get_order_exposes_payment_status(client, admin_header):
    order_response = client.post(
        "/api/v1/orders/",
        headers=admin_header,
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
    response = client.get(f"/api/v1/orders/{order_id}", headers=admin_header)
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


def test_webhook_requires_signature_when_secret_is_configured(client, monkeypatch):
    from app.infrastructure.api.routers import payments as payments_router_module

    monkeypatch.setattr(payments_router_module.settings, "mp_webhook_secret", "secret")
    response = client.post(
        "/api/v1/payments/webhook",
        json={"type": "payment", "data": {"id": 123}},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Firma de webhook requerida"


def test_internal_bootstrap_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module.settings, "environment", "staging")

    response = client.post("/api/v1/internal/bootstrap")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token interno invalido."


def test_internal_bootstrap_db_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    missing = client.post("/api/v1/internal/bootstrap-db")
    invalid = client.post("/api/v1/internal/bootstrap-db", headers={"X-Internal-Token": "wrong"})

    assert missing.status_code == 403
    assert invalid.status_code == 403
    assert missing.json()["detail"] == "Forbidden"
    assert invalid.json()["detail"] == "Forbidden"


def test_internal_bootstrap_db_runs_migrations(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    state = {"migrated": False}

    async def fake_run_alembic_upgrade():
        state["migrated"] = True

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "_run_alembic_upgrade", fake_run_alembic_upgrade)

    response = client.post("/api/v1/internal/bootstrap-db", headers={"X-Internal-Token": "secret-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Database migrated successfully"}
    assert state["migrated"] is True


def test_internal_bootstrap_db_returns_safe_error(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    async def fake_run_alembic_upgrade():
        raise RuntimeError("secret connection detail")

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "_run_alembic_upgrade", fake_run_alembic_upgrade)

    response = client.post("/api/v1/internal/bootstrap-db", headers={"X-Internal-Token": "secret-token"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Database migration failed."


def test_internal_pos_catalog_sync_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    missing = client.post("/api/v1/internal/pos/catalog-sync")
    invalid = client.post("/api/v1/internal/pos/catalog-sync", headers={"X-Internal-Token": "wrong"})

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_internal_pos_catalog_audit_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    missing = client.get("/api/v1/internal/pos/catalog-audit")
    invalid = client.get("/api/v1/internal/pos/catalog-audit", headers={"X-Internal-Token": "wrong"})

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_internal_pos_catalog_audit_returns_summary(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    class FakeAuditService:
        def __init__(self, _db):
            pass

        async def audit(self):
            return {
                "ok": True,
                "products": {
                    "total": 183,
                    "active": 183,
                    "available_for_ecommerce": 183,
                    "without_price": 0,
                    "without_category": 0,
                    "without_sku": 0,
                    "without_image": 12,
                    "duplicate_skus": [],
                    "duplicate_pos_product_ids": [],
                },
                "promotions": {
                    "total": 6,
                    "active": 6,
                    "without_price": 0,
                    "without_code": 0,
                    "without_image": 1,
                    "duplicate_codes": [],
                },
                "categories": {
                    "total": 4,
                    "names": ["Bebidas", "Handrolls", "Rolls", "Tablas"],
                },
                "branches": {
                    "total": 0,
                    "active": 0,
                },
            }

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "PosCatalogAuditService", FakeAuditService)

    response = client.get("/api/v1/internal/pos/catalog-audit", headers={"X-Internal-Token": "secret-token"})

    assert response.status_code == 200
    assert response.json()["products"]["total"] == 183
    assert response.json()["products"]["without_image"] == 12
    assert response.json()["promotions"]["without_image"] == 1


def test_internal_pos_catalog_audit_details_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    missing = client.get("/api/v1/internal/pos/catalog-audit/details")
    invalid = client.get("/api/v1/internal/pos/catalog-audit/details", headers={"X-Internal-Token": "wrong"})

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_internal_pos_catalog_audit_details_returns_detail_lists(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    class FakeAuditService:
        def __init__(self, _db):
            pass

        async def details(self):
            return {
                "products_without_price": [
                    {
                        "sku": "POS-001",
                        "name": "Producto sin precio",
                        "category": "Rolls",
                        "subcategory": None,
                        "price": 0,
                        "is_available": True,
                    }
                ],
                "products_without_image": [],
                "promotions_without_image": [
                    {
                        "code": "PROMO-1",
                        "name": "Promo sin imagen",
                        "price": 9990,
                        "is_active": True,
                    }
                ],
            }

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "PosCatalogAuditService", FakeAuditService)

    response = client.get(
        "/api/v1/internal/pos/catalog-audit/details",
        headers={"X-Internal-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["products_without_price"][0]["sku"] == "POS-001"
    assert response.json()["promotions_without_image"][0]["code"] == "PROMO-1"


def test_internal_catalog_image_assignment_import_requires_valid_token(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    missing = client.post("/api/v1/internal/catalog/image-assignments/import")
    invalid = client.post(
        "/api/v1/internal/catalog/image-assignments/import",
        headers={"X-Internal-Token": "wrong"},
    )

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_internal_catalog_image_assignment_import_runs_default_csv(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module
    from scripts.import_product_image_assignments import ProductImageImportResult

    captured = {}

    def fake_load_assignments(csv_path):
        captured["csv_path"] = csv_path
        return ["assignment-1", "assignment-2"]

    async def fake_apply_assignments(db, assignments, *, dry_run, fail_on_missing):
        captured["db"] = db
        captured["assignments"] = assignments
        captured["dry_run"] = dry_run
        captured["fail_on_missing"] = fail_on_missing
        return ProductImageImportResult(
            received=2,
            updated=1,
            skipped=1,
            missing=["CAS-EMP-MISSING"],
            errors=[],
        )

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "load_assignments", fake_load_assignments)
    monkeypatch.setattr(internal_router_module, "apply_product_image_assignments", fake_apply_assignments)

    response = client.post(
        "/api/v1/internal/catalog/image-assignments/import",
        headers={"X-Internal-Token": "secret-token"},
        json={"dry_run": True, "fail_on_missing": True},
    )

    assert response.status_code == 200
    assert captured["csv_path"].as_posix().endswith("exports/empanadas_product_image_assignments.csv")
    assert captured["assignments"] == ["assignment-1", "assignment-2"]
    assert captured["dry_run"] is True
    assert captured["fail_on_missing"] is True
    assert response.json() == {
        "dry_run": True,
        "total_rows": 2,
        "updated": 1,
        "skipped": 1,
        "missing": ["CAS-EMP-MISSING"],
        "errors": [],
    }


def test_internal_catalog_image_assignment_import_rejects_paths_outside_exports(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")

    response = client.post(
        "/api/v1/internal/catalog/image-assignments/import",
        headers={"X-Internal-Token": "secret-token"},
        json={"csv_path": "../.env", "dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV path must be inside exports/."


def test_internal_pos_catalog_sync_returns_summary(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    class FakeSyncResult:
        def to_dict(self):
            return {
                "source": "pos",
                "products": {
                    "received": 3,
                    "created": 2,
                    "updated": 1,
                    "deactivated": 0,
                },
                "promotions": {
                    "received": 1,
                    "created": 1,
                    "updated": 0,
                    "deactivated": 0,
                },
                "branches": {
                    "received": 0,
                    "created": 0,
                    "updated": 0,
                    "deactivated": 0,
                },
                "categories_created": 1,
                "categories_updated": 0,
                "skipped": 0,
                "errors": [],
            }

    class FakeSyncService:
        def __init__(self, _db):
            pass

        async def sync(self):
            return FakeSyncResult()

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module, "PosCatalogSyncService", FakeSyncService)

    response = client.post("/api/v1/internal/pos/catalog-sync", headers={"X-Internal-Token": "secret-token"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "source": "pos",
        "products": {
            "received": 3,
            "created": 2,
            "updated": 1,
            "deactivated": 0,
        },
        "promotions": {
            "received": 1,
            "created": 1,
            "updated": 0,
            "deactivated": 0,
        },
        "branches": {
            "received": 0,
            "created": 0,
            "updated": 0,
            "deactivated": 0,
        },
        "categories_created": 1,
        "categories_updated": 0,
        "skipped": 0,
        "errors": [],
    }


def test_internal_pos_catalog_sync_returns_controlled_pos_error(client, monkeypatch):
    from app.infrastructure.api.routers import internal as internal_router_module

    class FakeSyncService:
        def __init__(self, _db):
            pass

        async def sync(self):
            raise internal_router_module.PosClientError(
                "POS rejected token secret-token and pos-token",
                status_code=403,
                provider_status_code=403,
            )

    monkeypatch.setattr(internal_router_module.settings, "internal_bootstrap_token", "secret-token")
    monkeypatch.setattr(internal_router_module.settings, "pos_internal_token", "pos-token")
    monkeypatch.setattr(internal_router_module, "PosCatalogSyncService", FakeSyncService)

    response = client.post("/api/v1/internal/pos/catalog-sync", headers={"X-Internal-Token": "secret-token"})

    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "POS rejected token *** and ***"}
    assert "secret-token" not in str(response.json())
    assert "pos-token" not in str(response.json())


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
