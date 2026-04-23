from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.domain.models.entities import Coupon, Order, Product, User
from app.domain.models.enums import DeliveryType, OrderStatus, PaymentStatus, TicketTag, UserRole
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


def build_product() -> Product:
    return Product(
        id=1,
        category_id=1,
        sku="SKU-001",
        name="Yakero Roll",
        slug="yakero-roll",
        description="Test product",
        price=Decimal("4990"),
        image_url=None,
        ticket_tag=TicketTag.COCINA_SUSHI,
        is_available=True,
        sort_order=1,
        modifier_groups=[],
    )


class FakeUserRepository:
    users_by_id: dict[int, User] = {}
    users_by_email: dict[str, User] = {}
    next_id = 1

    def __init__(self, _db):
        self._db = _db

    @classmethod
    def reset(cls):
        user = build_user()
        cls.users_by_id = {user.id: user}
        cls.users_by_email = {user.email: user}
        cls.next_id = 2

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


class FakeProductRepository:
    def __init__(self, _db):
        self._product = build_product()

    async def get_all_active(self):
        return [self._product]

    async def get_by_id(self, product_id: int):
        return self._product if product_id == self._product.id else None

    async def get_by_category(self, _category_id: int):
        return [self._product]

    async def get_by_slug(self, slug: str):
        return self._product if slug == self._product.slug else None

    async def search(self, query: str):
        return [self._product] if query.lower() in self._product.name.lower() else []


class FakePromotionRepository:
    def __init__(self, _db):
        self._db = _db

    async def get_all_active(self):
        return []

    async def get_by_id(self, _promotion_id: int):
        return None


class FakeAddressRepository:
    def __init__(self, _db):
        self._db = _db

    async def get_by_user(self, _user_id: int):
        return []

    async def get_by_id(self, _address_id: int):
        return None

    async def create(self, address):
        return replace(address, id=1)

    async def update(self, address):
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
