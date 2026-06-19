from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application.use_cases.orders.pos_sync import PosOrderSyncService
from app.domain.models.entities import CheckoutSession, Order, OrderItem, Payment, Product, Promotion
from app.domain.models.enums import DeliveryType, OrderStatus, PaymentStatus, TicketTag
from app.infrastructure.clients import PosClientError


class FakeOrderRepo:
    def __init__(self):
        self.success_calls = []
        self.failed_calls = []

    async def mark_pos_sync_success(self, order_id, pos_sale_id, response):
        self.success_calls.append((order_id, pos_sale_id, response))
        order = _order()
        order.pos_sale_id = pos_sale_id
        order.pos_sync_status = "synced"
        order.pos_sync_response = response
        return order

    async def mark_pos_sync_failed(self, order_id, error, response=None):
        self.failed_calls.append((order_id, error, response))
        order = _order()
        order.pos_sync_status = "failed"
        order.pos_sync_error = error
        order.pos_sync_response = response
        return order


class FakeProductRepo:
    async def get_by_id(self, product_id):
        return Product(
            id=product_id,
            category_id=1,
            sku="SKU-001",
            name="Roll",
            slug="roll",
            subcategory=None,
            description=None,
            price=Decimal("5000"),
            image_url=None,
            ticket_tag=TicketTag.COCINA_SUSHI,
            is_available=True,
            sort_order=1,
            modifier_groups=[],
        )


class FakePromotionRepo:
    async def get_by_id(self, promotion_id):
        return Promotion(
            id=promotion_id,
            external_code="PROMO-001",
            name="Promo",
            description=None,
            promotion_type="bundle",
            value=Decimal("9000"),
            image_url=None,
            is_active=True,
            starts_at=None,
            ends_at=None,
            slots=[],
        )


class FakePosClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"accepted": True, "pos_sale_id": "SALE-1"}
        self.error = error
        self.calls = []

    async def send_order_to_pos(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_paid_order_sync_sends_pos_once_with_dry_run(monkeypatch):
    monkeypatch.setattr("app.application.use_cases.orders.pos_sync.settings.pos_ecommerce_dry_run", True)
    order_repo = FakeOrderRepo()
    pos_client = FakePosClient()
    service = _service(order_repo, pos_client)

    synced = await service.sync_paid_order(
        order=_order(),
        checkout_session=_checkout_session(),
        payment=_payment(),
        total_paid=Decimal("12000"),
    )

    assert synced.pos_sale_id == "SALE-1"
    assert len(pos_client.calls) == 1
    payload = pos_client.calls[0]
    assert payload["dry_run"] is True
    assert payload["external_order_id"] == "checkout-ref"
    assert payload["external_payment_id"] == "mp-123"
    assert payload["branch_external_code"] == "BR-1"
    assert payload["items"][0]["type"] == "product"
    assert payload["items"][0]["external_code"] == "SKU-001"
    assert payload["totals"]["total_paid"] == 12000
    assert order_repo.success_calls[0][1] == "SALE-1"


@pytest.mark.asyncio
async def test_paid_order_sync_does_not_resend_when_pos_sale_id_exists():
    order = _order()
    order.pos_sale_id = "SALE-EXISTING"
    order_repo = FakeOrderRepo()
    pos_client = FakePosClient()

    synced = await _service(order_repo, pos_client).sync_paid_order(
        order=order,
        checkout_session=_checkout_session(),
        payment=_payment(),
        total_paid=Decimal("12000"),
    )

    assert synced.pos_sale_id == "SALE-EXISTING"
    assert pos_client.calls == []
    assert order_repo.success_calls == []


@pytest.mark.asyncio
async def test_paid_order_sync_saves_duplicate_pos_sale_id():
    order_repo = FakeOrderRepo()
    pos_client = FakePosClient({"accepted": False, "duplicate": True, "pos_sale_id": "SALE-DUP"})

    synced = await _service(order_repo, pos_client).sync_paid_order(
        order=_order(),
        checkout_session=_checkout_session(),
        payment=_payment(),
        total_paid=Decimal("12000"),
    )

    assert synced.pos_sale_id == "SALE-DUP"
    assert order_repo.failed_calls == []


@pytest.mark.asyncio
async def test_paid_order_sync_marks_failed_when_pos_errors():
    order_repo = FakeOrderRepo()
    pos_client = FakePosClient(error=PosClientError("POS unavailable", status_code=502))

    synced = await _service(order_repo, pos_client).sync_paid_order(
        order=_order(),
        checkout_session=_checkout_session(),
        payment=_payment(),
        total_paid=Decimal("12000"),
    )

    assert synced.pos_sync_status == "failed"
    assert order_repo.failed_calls[0][1] == "POS unavailable"


@pytest.mark.asyncio
async def test_promotion_item_uses_promotion_external_code():
    order = _order(
        items=[
            OrderItem(
                id=2,
                order_id=1,
                product_id=None,
                promotion_id=10,
                promotion_slot_id=None,
                product_name="Promo",
                quantity=1,
                unit_price=Decimal("9000"),
                total_price=Decimal("9000"),
                ticket_tag=TicketTag.COCINA_SUSHI,
                notes=None,
                config_json=None,
                modifiers=[],
            )
        ]
    )
    pos_client = FakePosClient()

    await _service(FakeOrderRepo(), pos_client).sync_paid_order(
        order=order,
        checkout_session=_checkout_session(),
        payment=_payment(),
        total_paid=Decimal("9000"),
    )

    assert pos_client.calls[0]["items"][0]["type"] == "promotion"
    assert pos_client.calls[0]["items"][0]["external_code"] == "PROMO-001"


def _service(order_repo, pos_client):
    return PosOrderSyncService(
        order_repo=order_repo,
        product_repo=FakeProductRepo(),
        promotion_repo=FakePromotionRepo(),
        pos_client=pos_client,
    )


def _order(items=None):
    return Order(
        id=1,
        user_id=None,
        guest_email="guest@test.cl",
        guest_phone="+56912345678",
        address_id=1,
        delivery_type=DeliveryType.DELIVERY,
        status=OrderStatus.PAID,
        payment_status=PaymentStatus.PAID,
        subtotal=Decimal("10000"),
        delivery_fee=Decimal("2000"),
        discount=Decimal("0"),
        points_used=0,
        total=Decimal("12000"),
        payment_provider="mercadopago",
        mp_preference_id="pref-1",
        mp_payment_id="mp-123",
        mp_payment_status="approved",
        notes=None,
        items=items
        or [
            OrderItem(
                id=1,
                order_id=1,
                product_id=1,
                promotion_id=None,
                promotion_slot_id=None,
                product_name="Roll",
                quantity=2,
                unit_price=Decimal("5000"),
                total_price=Decimal("10000"),
                ticket_tag=TicketTag.COCINA_SUSHI,
                notes="sin cebolla",
                config_json=None,
                modifiers=[],
            )
        ],
        created_at=datetime.now(UTC),
        paid_at=datetime.now(UTC),
        delivery_address_snapshot={
            "street": "Av Siempre Viva",
            "number": "123",
            "commune": "Providencia",
            "notes": "Casa",
            "latitude": -33.4,
            "longitude": -70.6,
        },
    )


def _checkout_session():
    return CheckoutSession(
        id=1,
        session_token="checkout-ref",
        user_id=None,
        guest_email="guest@test.cl",
        guest_phone="+56912345678",
        address_id=1,
        delivery_type=DeliveryType.DELIVERY,
        status="paid",
        payment_provider="mercadopago",
        mp_preference_id="pref-1",
        mp_init_point=None,
        mp_sandbox_init_point=None,
        cart_snapshot={},
        customer_data={
            "name": "Cliente Test",
            "email": "guest@test.cl",
            "phone": "+56912345678",
            "branch_external_code": "BR-1",
        },
        pricing_snapshot=None,
        delivery_address_snapshot=None,
        coupon_code=None,
        subtotal=Decimal("10000"),
        delivery_fee=Decimal("2000"),
        discount=Decimal("0"),
        points_used=0,
        total=Decimal("12000"),
        created_order_id=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


def _payment():
    return Payment(
        id=1,
        checkout_session_id=1,
        order_id=1,
        provider="mercadopago",
        provider_payment_id="mp-123",
        provider_preference_id="pref-1",
        status="pagado",
        provider_status="approved",
        amount=Decimal("12000"),
        currency="CLP",
        raw_payload={},
        approved_at=datetime.now(UTC),
    )
