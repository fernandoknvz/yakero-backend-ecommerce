import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from app.application.use_cases.orders.create_order import CreateOrderUseCase
from app.application.dtos.schemas import CreateOrderInput, OrderItemInput
from app.domain.models.entities import Product, ModifierGroup, ModifierOption, Order
from app.domain.models.enums import (
    DeliveryType, TicketTag, ModifierType, OrderStatus, PaymentStatus,
)
from app.domain.exceptions import ModifierValidationError, ValidationError


def make_product(required_group: bool = True) -> Product:
    option = ModifierOption(id=1, group_id=1, name="Salmón", extra_price=Decimal("0"), is_available=True)
    group = ModifierGroup(
        id=1, product_id=1, name="Proteína",
        modifier_type=ModifierType.SINGLE,
        min_selections=1, max_selections=1,
        is_required=required_group, options=[option],
    )
    return Product(
        id=1, category_id=1, sku="P001", name="California Roll",
        slug="california-roll", description=None, price=Decimal("4990"),
        image_url=None, ticket_tag=TicketTag.COCINA_SUSHI,
        is_available=True, sort_order=1, modifier_groups=[group],
    )


def make_order_repo(saved_order: Order) -> AsyncMock:
    repo = AsyncMock()
    repo.create.return_value = saved_order
    return repo


def make_product_repo(product: Product) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = product
    return repo


def make_delivery_service(fee: Decimal = Decimal("1490")) -> AsyncMock:
    svc = AsyncMock()
    svc.calculate.return_value = fee
    return svc


def make_points_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def saved_order() -> Order:
    return Order(
        id=42, user_id=1, guest_email=None, guest_phone=None,
        address_id=None, delivery_type=DeliveryType.PICKUP,
        status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING,
        subtotal=Decimal("4990"), delivery_fee=Decimal("0"),
        discount=Decimal("0"), points_used=0, total=Decimal("4990"),
        mp_preference_id=None, mp_payment_id=None, mp_payment_status=None,
        notes=None, items=[],
    )


@pytest.mark.asyncio
async def test_create_order_pickup_no_modifiers_required(saved_order):
    """Producto sin modificadores requeridos → pedido creado correctamente."""
    product = make_product(required_group=False)
    uc = CreateOrderUseCase(
        order_repo=make_order_repo(saved_order),
        product_repo=make_product_repo(product),
        promotion_repo=AsyncMock(),
        user_repo=AsyncMock(),
        address_repo=AsyncMock(),
        coupon_repo=AsyncMock(),
        delivery_service=make_delivery_service(),
        points_service=make_points_service(),
    )
    data = CreateOrderInput(
        delivery_type=DeliveryType.PICKUP,
        items=[OrderItemInput(product_id=1, quantity=1)],
    )
    order = await uc.execute(data, user_id=1)
    assert order.id == 42


@pytest.mark.asyncio
async def test_create_order_missing_required_modifier():
    """Modificador obligatorio sin selección → lanza ModifierValidationError."""
    product = make_product(required_group=True)
    uc = CreateOrderUseCase(
        order_repo=AsyncMock(),
        product_repo=make_product_repo(product),
        promotion_repo=AsyncMock(),
        user_repo=AsyncMock(),
        address_repo=AsyncMock(),
        coupon_repo=AsyncMock(),
        delivery_service=make_delivery_service(),
        points_service=make_points_service(),
    )
    data = CreateOrderInput(
        delivery_type=DeliveryType.PICKUP,
        items=[OrderItemInput(product_id=1, quantity=1, selected_modifiers=[])],
    )
    with pytest.raises(ModifierValidationError):
        await uc.execute(data, user_id=1)


@pytest.mark.asyncio
async def test_delivery_requires_address_id():
    """delivery_type=delivery sin address_id → Pydantic lanza ValidationError."""
    with pytest.raises(Exception):
        CreateOrderInput(
            delivery_type=DeliveryType.DELIVERY,
            items=[OrderItemInput(product_id=1)],
            # address_id ausente
        )


@pytest.mark.asyncio
async def test_order_status_transitions():
    """Verifica que las transiciones de estado sean correctas."""
    from app.domain.models.entities import Order
    order = Order(
        id=1, user_id=1, guest_email=None, guest_phone=None, address_id=None,
        delivery_type=DeliveryType.PICKUP, status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING, subtotal=Decimal("0"),
        delivery_fee=Decimal("0"), discount=Decimal("0"), points_used=0,
        total=Decimal("0"), mp_preference_id=None, mp_payment_id=None,
        mp_payment_status=None, notes=None,
    )
    assert order.can_transition_to(OrderStatus.PAID) is True
    assert order.can_transition_to(OrderStatus.PREPARING) is False  # no se puede saltar
    assert order.can_transition_to(OrderStatus.DELIVERED) is False
