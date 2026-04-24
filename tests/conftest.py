from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.domain.models.entities import (
    Address,
    Category,
    Coupon,
    ModifierGroup,
    ModifierOption,
    Order,
    Product,
    Promotion,
    User,
)
from app.domain.models.enums import (
    DeliveryType,
    ModifierType,
    OrderStatus,
    PaymentStatus,
    TicketTag,
    UserRole,
)
from app.infrastructure.database.session import get_db
from app.main import app


def build_user(user_id: int = 1, email: str = "tester@yakero.cl") -> User:
    return User(
        id=user_id,
        email=email,
        password_hash="$2b$12$ySv1M4BrJxS1M7P9h8Wwbe7M.h1wPq6Q5xSh7sM1T8fLMQwW9z8hK",
        first_name="Test",
        last_name="User",
        phone="+56911111111",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_guest=False,
        points_balance=120,
        created_at=datetime.now(UTC),
    )


def build_demo_user() -> User:
    return User(
        id=2,
        email="feradmin@example.com",
        password_hash="hashed::Admin123456",
        first_name="Fernando",
        last_name="Admin",
        phone="+56911112222",
        role=UserRole.ADMIN,
        is_active=True,
        is_guest=False,
        points_balance=0,
        created_at=datetime.now(UTC),
    )


def build_categories() -> list[Category]:
    return [
        Category(
            id=1,
            name="Rolls",
            slug="rolls",
            ticket_tag=TicketTag.COCINA_SUSHI,
            image_url=None,
            sort_order=1,
            is_active=True,
        ),
        Category(
            id=2,
            name="Bebidas",
            slug="bebidas",
            ticket_tag=TicketTag.CAJA,
            image_url=None,
            sort_order=2,
            is_active=True,
        ),
    ]


def build_products() -> list[Product]:
    protein_option = ModifierOption(
        id=1,
        group_id=1,
        name="Salmon",
        extra_price=Decimal("500"),
        is_available=True,
    )
    sauce_option = ModifierOption(
        id=2,
        group_id=2,
        name="Salsa teriyaki",
        extra_price=Decimal("250"),
        is_available=True,
    )
    return [
        Product(
            id=1,
            category_id=1,
            sku="SKU-001",
            name="Yakero Roll",
            slug="yakero-roll",
            description="Roll premium",
            price=Decimal("4990"),
            image_url="https://img.test/yakero-roll.png",
            ticket_tag=TicketTag.COCINA_SUSHI,
            is_available=True,
            sort_order=1,
            modifier_groups=[
                ModifierGroup(
                    id=1,
                    product_id=1,
                    name="Proteina",
                    modifier_type=ModifierType.SINGLE,
                    min_selections=1,
                    max_selections=1,
                    is_required=True,
                    options=[protein_option],
                ),
                ModifierGroup(
                    id=2,
                    product_id=1,
                    name="Salsas",
                    modifier_type=ModifierType.MULTIPLE,
                    min_selections=0,
                    max_selections=2,
                    is_required=False,
                    options=[sauce_option],
                ),
            ],
        ),
        Product(
            id=2,
            category_id=2,
            sku="SKU-002",
            name="Limonada",
            slug="limonada",
            description="Limonada natural",
            price=Decimal("1990"),
            image_url=None,
            ticket_tag=TicketTag.CAJA,
            is_available=True,
            sort_order=2,
            modifier_groups=[],
        ),
    ]


def build_promotions() -> list[Promotion]:
    return [
        Promotion(
            id=10,
            name="Promo sushi night",
            description="Combo nocturno",
            promotion_type="bundle",
            value=Decimal("8990"),
            image_url=None,
            is_active=True,
            starts_at=None,
            ends_at=None,
            slots=[],
        )
    ]


class FakeUserRepository:
    users_by_id: dict[int, User] = {}
    users_by_email: dict[str, User] = {}
    next_id = 1

    def __init__(self, _db):
        self._db = _db

    @classmethod
    def reset(cls):
        user = build_user()
        demo_user = build_demo_user()
        cls.users_by_id = {user.id: user, demo_user.id: demo_user}
        cls.users_by_email = {user.email: user, demo_user.email: demo_user}
        cls.next_id = 3

    async def get_by_id(self, user_id: int):
        return self.users_by_id.get(user_id)

    async def get_by_email(self, email: str):
        return self.users_by_email.get(email.lower())

    async def create(self, user: User):
        created = replace(user, id=self.next_id, created_at=user.created_at or datetime.now(UTC))
        self.users_by_id[created.id] = created
        self.users_by_email[created.email] = created
        self.next_id += 1
        return created

    async def update(self, user: User):
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        return user

    async def add_points(self, user_id: int, points: int):
        user = self.users_by_id[user_id]
        updated = replace(user, points_balance=user.points_balance + points)
        self.users_by_id[user_id] = updated
        self.users_by_email[updated.email] = updated


class FakeCategoryRepository:
    def __init__(self, _db):
        self._categories = build_categories()

    async def get_all_active(self):
        return self._categories

    async def get_by_id(self, category_id: int):
        return next((category for category in self._categories if category.id == category_id), None)


class FakeProductRepository:
    def __init__(self, _db):
        self._products = build_products()

    async def get_all_active(self):
        return self._products

    async def get_by_id(self, product_id: int):
        return next((product for product in self._products if product.id == product_id), None)

    async def get_by_category(self, category_id: int):
        return [product for product in self._products if product.category_id == category_id]

    async def get_by_slug(self, slug: str):
        return next((product for product in self._products if product.slug == slug), None)

    async def search(self, query: str):
        lowered = query.lower()
        return [product for product in self._products if lowered in product.name.lower()]


class FakePromotionRepository:
    def __init__(self, _db):
        self._promotions = build_promotions()

    async def get_all_active(self):
        return self._promotions

    async def get_by_id(self, promotion_id: int):
        return next((promotion for promotion in self._promotions if promotion.id == promotion_id), None)


class FakeAddressRepository:
    def __init__(self, _db):
        self._db = _db
        self._addresses = {
            1: Address(
                id=1,
                user_id=1,
                label="Casa",
                street="Av. Siempre Viva",
                number="742",
                commune="Providencia",
                city="Santiago",
                latitude=-33.44,
                longitude=-70.65,
                notes="Depto 12",
                is_default=True,
            )
        }

    async def get_by_user(self, user_id: int):
        return [address for address in self._addresses.values() if address.user_id == user_id]

    async def get_by_id(self, address_id: int):
        return self._addresses.get(address_id)

    async def create(self, address):
        return replace(address, id=2)

    async def update(self, address):
        self._addresses[address.id] = address
        return address

    async def delete(self, _address_id: int):
        return None

    async def set_default(self, _user_id: int, _address_id: int):
        return None


class FakeCouponRepository:
    def __init__(self, _db):
        self._db = _db

    async def get_by_code(self, code: str):
        if code.upper() != "SAVE10":
            return None
        return Coupon(
            id=1,
            code="SAVE10",
            discount_type="percent",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("3000"),
            max_uses=10,
            uses_count=0,
            user_id=None,
            expires_at=None,
            is_active=True,
        )

    async def increment_uses(self, _coupon_id: int):
        return None


class FakeOrderRepository:
    orders: dict[int, Order] = {}
    next_id = 1

    def __init__(self, _db):
        self._db = _db

    @classmethod
    def reset(cls):
        cls.orders = {}
        cls.next_id = 1

    async def get_by_id(self, order_id: int):
        return self.orders.get(order_id)

    async def get_by_user(self, user_id: int, skip: int = 0, limit: int = 20):
        orders = [order for order in self.orders.values() if order.user_id == user_id]
        return orders[skip : skip + limit]

    async def get_pending_for_pos(self):
        return [order for order in self.orders.values() if order.status == OrderStatus.PAID]

    async def create(self, order: Order):
        items = [
            replace(item, id=index, order_id=self.next_id)
            for index, item in enumerate(order.items, start=1)
        ]
        created = replace(
            order,
            id=self.next_id,
            items=items,
            created_at=order.created_at or datetime.now(UTC),
        )
        self.orders[created.id] = created
        self.next_id += 1
        return created

    async def update_status(self, order_id: int, status: OrderStatus):
        order = self.orders[order_id]
        updated = replace(order, status=status)
        self.orders[order_id] = updated
        return updated

    async def update_payment(self, order_id: int, mp_payment_id: str, mp_status: str):
        order = self.orders[order_id]
        updated = replace(order, mp_payment_id=mp_payment_id, mp_payment_status=mp_status)
        self.orders[order_id] = updated
        return updated

    async def update_mp_preference(self, order_id: int, preference_id: str):
        order = self.orders[order_id]
        updated = replace(order, mp_preference_id=preference_id)
        self.orders[order_id] = updated
        return updated

    async def get_by_mp_preference(self, preference_id: str):
        for order in self.orders.values():
            if order.mp_preference_id == preference_id:
                return order
        return None


class FakeMercadoPagoService:
    async def create_preference(self, _order: Order, back_urls: dict):
        return "pref_test_123"

    def verify_webhook_signature(self, _data: str, _signature: str):
        return False


@pytest.fixture(autouse=True)
def fake_app_dependencies(monkeypatch):
    from app.application.use_cases.auth import auth_use_cases as auth_use_cases_module
    from app.infrastructure.api.routers import auth as auth_router_module
    from app.infrastructure.api.routers import catalog as catalog_router_module
    from app.infrastructure.api.routers import internal as internal_router_module
    from app.infrastructure.api.routers import operations as operations_router_module
    from app.infrastructure.api.routers import orders as orders_router_module
    from app.infrastructure.api.routers import users as users_router_module
    from app.infrastructure.api.routers import webhooks as webhooks_router_module
    import app.auth as auth_module

    FakeUserRepository.reset()
    FakeOrderRepository.reset()

    monkeypatch.setattr(auth_router_module, "SQLUserRepository", FakeUserRepository)
    monkeypatch.setattr(users_router_module, "SQLUserRepository", FakeUserRepository)
    monkeypatch.setattr(users_router_module, "SQLAddressRepository", FakeAddressRepository)
    monkeypatch.setattr(orders_router_module, "SQLUserRepository", FakeUserRepository)
    monkeypatch.setattr(orders_router_module, "SQLOrderRepository", FakeOrderRepository)
    monkeypatch.setattr(orders_router_module, "SQLProductRepository", FakeProductRepository)
    monkeypatch.setattr(orders_router_module, "SQLAddressRepository", FakeAddressRepository)
    monkeypatch.setattr(orders_router_module, "SQLCouponRepository", FakeCouponRepository)
    monkeypatch.setattr(orders_router_module, "SQLPromotionRepository", FakePromotionRepository)
    monkeypatch.setattr(orders_router_module, "MercadoPagoService", FakeMercadoPagoService)
    monkeypatch.setattr(operations_router_module, "SQLCouponRepository", FakeCouponRepository)
    monkeypatch.setattr(catalog_router_module, "SQLCategoryRepository", FakeCategoryRepository)
    monkeypatch.setattr(catalog_router_module, "SQLProductRepository", FakeProductRepository)
    monkeypatch.setattr(catalog_router_module, "SQLPromotionRepository", FakePromotionRepository)
    monkeypatch.setattr(internal_router_module, "SQLOrderRepository", FakeOrderRepository)
    monkeypatch.setattr(webhooks_router_module, "SQLOrderRepository", FakeOrderRepository)
    monkeypatch.setattr(webhooks_router_module, "MercadoPagoService", FakeMercadoPagoService)
    monkeypatch.setattr(auth_module, "SQLUserRepository", FakeUserRepository)
    monkeypatch.setattr(auth_use_cases_module.pwd_context, "hash", lambda secret: f"hashed::{secret}")
    monkeypatch.setattr(
        auth_use_cases_module.pwd_context,
        "verify",
        lambda secret, hashed: hashed == f"hashed::{secret}",
    )

    async def override_get_db():
        yield object()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_header():
    token = create_access_token(user_id=1, role=UserRole.CUSTOMER)
    return {"Authorization": f"Bearer {token}"}
