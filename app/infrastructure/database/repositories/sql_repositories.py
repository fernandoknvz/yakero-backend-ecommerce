from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ....domain.models.entities import (
    Order, OrderItem, OrderItemModifier,
    Product, Category, ModifierGroup, ModifierOption,
    Promotion, PromotionSlot, User, Address, Coupon, CheckoutSession, Payment,
)
from ....domain.models.enums import DeliveryType, OrderStatus
from ....domain.repositories.interfaces import (
    OrderRepository, ProductRepository, CategoryRepository,
    UserRepository, AddressRepository, PromotionRepository, CouponRepository,
    CheckoutSessionRepository, PaymentRepository,
)
from ..models.orm_models import (
    OrderORM, OrderItemORM, OrderItemModifierORM,
    ProductORM, CategoryORM, UserORM, AddressORM,
    PromotionORM, PromotionSlotORM, ModifierGroupORM, CouponORM,
    CheckoutSessionORM, PaymentORM,
)


# ─── Mappers ORM → Domain ─────────────────────────────────────────────────────

def _map_modifier_option(o) -> ModifierOption:
    return ModifierOption(
        id=o.id, group_id=o.group_id, name=o.name,
        extra_price=Decimal(o.extra_price), is_available=o.is_available,
    )

def _map_modifier_group(g) -> ModifierGroup:
    return ModifierGroup(
        id=g.id, product_id=g.product_id or 0, name=g.name,
        modifier_type=g.modifier_type, min_selections=g.min_selections,
        max_selections=g.max_selections, is_required=g.is_required,
        options=[_map_modifier_option(o) for o in g.options],
    )

def _map_product(p) -> Product:
    return Product(
        id=p.id, category_id=p.category_id, sku=p.sku, name=p.name,
        slug=p.slug, description=p.description, price=Decimal(p.price),
        image_url=p.image_url, ticket_tag=p.ticket_tag,
        is_available=p.is_available, sort_order=p.sort_order,
        modifier_groups=[_map_modifier_group(g) for g in p.modifier_groups],
    )

def _map_category(c) -> Category:
    return Category(
        id=c.id, name=c.name, slug=c.slug, ticket_tag=c.ticket_tag,
        image_url=c.image_url, sort_order=c.sort_order, is_active=c.is_active,
    )

def _map_promotion_slot(s) -> PromotionSlot:
    return PromotionSlot(
        id=s.id,
        promotion_id=s.promotion_id,
        slot_name=s.slot_name,
        pieces=s.pieces,
        ticket_tag=s.ticket_tag,
        modifier_groups=[_map_modifier_group(g) for g in s.modifier_groups],
    )

def _map_promotion(p) -> Promotion:
    return Promotion(
        id=p.id,
        name=p.name,
        description=p.description,
        promotion_type=p.promotion_type,
        value=Decimal(p.value),
        image_url=p.image_url,
        is_active=p.is_active,
        starts_at=p.starts_at,
        ends_at=p.ends_at,
        slots=[_map_promotion_slot(s) for s in p.slots],
    )

def _map_order_item(i) -> OrderItem:
    return OrderItem(
        id=i.id, order_id=i.order_id, product_id=i.product_id,
        promotion_id=i.promotion_id, promotion_slot_id=i.promotion_slot_id,
        product_name=i.product_name, quantity=i.quantity,
        unit_price=Decimal(i.unit_price), total_price=Decimal(i.total_price),
        ticket_tag=i.ticket_tag, notes=i.notes, config_json=i.config_json,
        modifiers=[
            OrderItemModifier(
                id=m.id, order_item_id=m.order_item_id,
                modifier_option_id=m.modifier_option_id,
                option_name=m.option_name, group_name=m.group_name,
                extra_price=Decimal(m.extra_price),
            )
            for m in i.modifiers
        ],
    )

def _map_order(o) -> Order:
    return Order(
        id=o.id, user_id=o.user_id, guest_email=o.guest_email,
        guest_phone=o.guest_phone, address_id=o.address_id,
        delivery_type=o.delivery_type, status=o.status,
        payment_status=o.payment_status, subtotal=Decimal(o.subtotal),
        delivery_fee=Decimal(o.delivery_fee), discount=Decimal(o.discount),
        points_used=o.points_used, total=Decimal(o.total),
        payment_provider=o.payment_provider,
        mp_preference_id=o.mp_preference_id, mp_payment_id=o.mp_payment_id,
        mp_payment_status=o.mp_payment_status, notes=o.notes,
        items=[_map_order_item(i) for i in o.items],
        created_at=o.created_at, paid_at=o.paid_at,
        ready_at=o.ready_at, delivered_at=o.delivered_at,
        delivery_address_snapshot=o.delivery_address_snapshot,
    )


def _map_checkout_session(s) -> CheckoutSession:
    return CheckoutSession(
        id=s.id,
        session_token=s.session_token,
        user_id=s.user_id,
        guest_email=s.guest_email,
        guest_phone=s.guest_phone,
        address_id=s.address_id,
        delivery_type=DeliveryType(s.delivery_type),
        status=s.status,
        payment_provider=s.payment_provider,
        mp_preference_id=s.mp_preference_id,
        mp_init_point=s.mp_init_point,
        mp_sandbox_init_point=s.mp_sandbox_init_point,
        cart_snapshot=s.cart_snapshot,
        customer_data=s.customer_data,
        pricing_snapshot=s.pricing_snapshot,
        delivery_address_snapshot=s.delivery_address_snapshot,
        coupon_code=s.coupon_code,
        subtotal=Decimal(s.subtotal),
        delivery_fee=Decimal(s.delivery_fee),
        discount=Decimal(s.discount),
        points_used=s.points_used,
        total=Decimal(s.total),
        created_order_id=s.created_order_id,
        expires_at=s.expires_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _map_payment(p) -> Payment:
    return Payment(
        id=p.id,
        checkout_session_id=p.checkout_session_id,
        order_id=p.order_id,
        provider=p.provider,
        provider_payment_id=p.provider_payment_id,
        provider_preference_id=p.provider_preference_id,
        status=p.status,
        provider_status=p.provider_status,
        amount=Decimal(p.amount) if p.amount is not None else None,
        currency=p.currency,
        raw_payload=p.raw_payload,
        approved_at=p.approved_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ─── Product Repository ───────────────────────────────────────────────────────

class SQLProductRepository(ProductRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    _load_opts = [
        selectinload(ProductORM.modifier_groups).selectinload(ModifierGroupORM.options)
    ]

    async def get_all_active(self) -> list[Product]:
        result = await self._db.execute(
            select(ProductORM)
            .where(ProductORM.is_available == True)
            .options(*self._load_opts)
            .order_by(ProductORM.sort_order)
        )
        return [_map_product(p) for p in result.scalars().all()]

    async def get_by_id(self, product_id: int) -> Optional[Product]:
        result = await self._db.execute(
            select(ProductORM)
            .where(ProductORM.id == product_id)
            .options(*self._load_opts)
        )
        p = result.scalar_one_or_none()
        return _map_product(p) if p else None

    async def get_by_category(self, category_id: int) -> list[Product]:
        result = await self._db.execute(
            select(ProductORM)
            .where(ProductORM.category_id == category_id, ProductORM.is_available == True)
            .options(*self._load_opts)
            .order_by(ProductORM.sort_order)
        )
        return [_map_product(p) for p in result.scalars().all()]

    async def get_by_slug(self, slug: str) -> Optional[Product]:
        result = await self._db.execute(
            select(ProductORM)
            .where(ProductORM.slug == slug)
            .options(*self._load_opts)
        )
        p = result.scalar_one_or_none()
        return _map_product(p) if p else None

    async def search(self, query: str) -> list[Product]:
        result = await self._db.execute(
            select(ProductORM)
            .where(
                ProductORM.name.ilike(f"%{query}%"),
                ProductORM.is_available == True,
            )
            .options(*self._load_opts)
            .order_by(ProductORM.sort_order, ProductORM.name)
        )
        return [_map_product(p) for p in result.scalars().all()]


# Category Repository

class SQLCategoryRepository(CategoryRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_all_active(self) -> list[Category]:
        result = await self._db.execute(
            select(CategoryORM)
            .where(CategoryORM.is_active == True)
            .order_by(CategoryORM.sort_order)
        )
        return [_map_category(c) for c in result.scalars().all()]

    async def get_by_id(self, category_id: int) -> Optional[Category]:
        result = await self._db.execute(
            select(CategoryORM).where(CategoryORM.id == category_id)
        )
        c = result.scalar_one_or_none()
        return _map_category(c) if c else None


# Promotion Repository

class SQLPromotionRepository(PromotionRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    _load_opts = [
        selectinload(PromotionORM.slots)
        .selectinload(PromotionSlotORM.modifier_groups)
        .selectinload(ModifierGroupORM.options)
    ]

    async def get_all_active(self) -> list[Promotion]:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(PromotionORM)
            .where(
                PromotionORM.is_active == True,
                (PromotionORM.starts_at == None) | (PromotionORM.starts_at <= now),
                (PromotionORM.ends_at == None) | (PromotionORM.ends_at > now),
            )
            .options(*self._load_opts)
        )
        return [_map_promotion(p) for p in result.scalars().all()]

    async def get_by_id(self, promotion_id: int) -> Optional[Promotion]:
        result = await self._db.execute(
            select(PromotionORM)
            .where(PromotionORM.id == promotion_id)
            .options(*self._load_opts)
        )
        p = result.scalar_one_or_none()
        return _map_promotion(p) if p else None


# ─── Order Repository ─────────────────────────────────────────────────────────

class SQLOrderRepository(OrderRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    _load_opts = [
        selectinload(OrderORM.items).selectinload(OrderItemORM.modifiers)
    ]

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        result = await self._db.execute(
            select(OrderORM).where(OrderORM.id == order_id)
            .options(*self._load_opts)
        )
        o = result.scalar_one_or_none()
        return _map_order(o) if o else None

    async def get_by_user(self, user_id: int, skip: int = 0, limit: int = 20) -> list[Order]:
        result = await self._db.execute(
            select(OrderORM)
            .where(OrderORM.user_id == user_id)
            .options(*self._load_opts)
            .order_by(OrderORM.created_at.desc())
            .offset(skip).limit(limit)
        )
        return [_map_order(o) for o in result.scalars().all()]

    async def get_pending_for_pos(self) -> list[Order]:
        result = await self._db.execute(
            select(OrderORM)
            .where(OrderORM.status == OrderStatus.PAID)
            .options(*self._load_opts)
            .order_by(OrderORM.paid_at)
        )
        return [_map_order(o) for o in result.scalars().all()]

    async def create(self, order: Order) -> Order:
        orm = OrderORM(
            user_id=order.user_id, guest_email=order.guest_email,
            guest_phone=order.guest_phone, address_id=order.address_id,
            delivery_type=order.delivery_type, status=order.status,
            payment_status=order.payment_status, subtotal=order.subtotal,
            delivery_fee=order.delivery_fee, discount=order.discount,
            points_used=order.points_used, total=order.total,
            payment_provider=order.payment_provider,
            notes=order.notes,
            delivery_address_snapshot=order.delivery_address_snapshot,
        )
        self._db.add(orm)
        await self._db.flush()  # obtener ID

        for item in order.items:
            item_orm = OrderItemORM(
                order_id=orm.id, product_id=item.product_id,
                promotion_id=item.promotion_id,
                promotion_slot_id=item.promotion_slot_id,
                product_name=item.product_name, quantity=item.quantity,
                unit_price=item.unit_price, total_price=item.total_price,
                ticket_tag=item.ticket_tag, notes=item.notes,
                config_json=item.config_json,
            )
            self._db.add(item_orm)
            await self._db.flush()
            for mod in item.modifiers:
                self._db.add(OrderItemModifierORM(
                    order_item_id=item_orm.id,
                    modifier_option_id=mod.modifier_option_id,
                    option_name=mod.option_name, group_name=mod.group_name,
                    extra_price=mod.extra_price,
                ))

        await self._db.refresh(orm)
        return await self.get_by_id(orm.id)

    async def update_status(self, order_id: int, status: OrderStatus) -> Order:
        extra: dict = {}
        now = datetime.now(UTC)
        if status == OrderStatus.PAID:
            extra["paid_at"] = now
        elif status == OrderStatus.READY:
            extra["ready_at"] = now
        elif status in (OrderStatus.DELIVERED, OrderStatus.DISPATCHED):
            extra["delivered_at"] = now

        await self._db.execute(
            update(OrderORM)
            .where(OrderORM.id == order_id)
            .values(status=status, **extra)
        )
        return await self.get_by_id(order_id)

    async def update_payment(
        self,
        order_id: int,
        payment_provider: str,
        payment_status: str,
        mp_payment_id: str,
        mp_status: str,
        paid_at=None,
    ) -> Order:
        await self._db.execute(
            update(OrderORM)
            .where(OrderORM.id == order_id)
            .values(
                payment_provider=payment_provider,
                payment_status=payment_status,
                mp_payment_id=mp_payment_id,
                mp_payment_status=mp_status,
                paid_at=paid_at,
            )
        )
        return await self.get_by_id(order_id)

    async def update_mp_preference(
        self,
        order_id: int,
        preference_id: str,
        payment_provider: str,
        payment_status: str,
    ) -> Order:
        await self._db.execute(
            update(OrderORM)
            .where(OrderORM.id == order_id)
            .values(
                payment_provider=payment_provider,
                payment_status=payment_status,
                mp_preference_id=preference_id,
            )
        )
        return await self.get_by_id(order_id)

    async def get_by_mp_preference(self, preference_id: str) -> Optional[Order]:
        result = await self._db.execute(
            select(OrderORM)
            .where(OrderORM.mp_preference_id == preference_id)
            .options(*self._load_opts)
        )
        o = result.scalar_one_or_none()
        return _map_order(o) if o else None


class SQLCheckoutSessionRepository(CheckoutSessionRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def create(self, session: CheckoutSession) -> CheckoutSession:
        now = datetime.now(UTC)
        orm = CheckoutSessionORM(
            session_token=session.session_token,
            user_id=session.user_id,
            guest_email=session.guest_email,
            guest_phone=session.guest_phone,
            address_id=session.address_id,
            delivery_type=session.delivery_type.value,
            status=session.status,
            payment_provider=session.payment_provider,
            mp_preference_id=session.mp_preference_id,
            mp_init_point=session.mp_init_point,
            mp_sandbox_init_point=session.mp_sandbox_init_point,
            cart_snapshot=session.cart_snapshot,
            customer_data=session.customer_data,
            pricing_snapshot=session.pricing_snapshot,
            delivery_address_snapshot=session.delivery_address_snapshot,
            coupon_code=session.coupon_code,
            subtotal=session.subtotal,
            delivery_fee=session.delivery_fee,
            discount=session.discount,
            points_used=session.points_used,
            total=session.total,
            created_order_id=session.created_order_id,
            expires_at=session.expires_at,
            created_at=session.created_at or now,
            updated_at=session.updated_at or now,
        )
        self._db.add(orm)
        await self._db.flush()
        return await self.get_by_id(orm.id)

    async def get_by_id(self, session_id: int) -> Optional[CheckoutSession]:
        result = await self._db.execute(
            select(CheckoutSessionORM).where(CheckoutSessionORM.id == session_id)
        )
        session = result.scalar_one_or_none()
        return _map_checkout_session(session) if session else None

    async def get_by_external_reference(self, external_reference: str) -> Optional[CheckoutSession]:
        result = await self._db.execute(
            select(CheckoutSessionORM).where(CheckoutSessionORM.session_token == external_reference)
        )
        session = result.scalar_one_or_none()
        return _map_checkout_session(session) if session else None

    async def update_preference(
        self,
        session_id: int,
        preference_id: str,
        init_point: Optional[str],
        sandbox_init_point: Optional[str],
    ) -> CheckoutSession:
        await self._db.execute(
            update(CheckoutSessionORM)
            .where(CheckoutSessionORM.id == session_id)
            .values(
                mp_preference_id=preference_id,
                mp_init_point=init_point,
                mp_sandbox_init_point=sandbox_init_point,
                updated_at=datetime.now(UTC),
            )
        )
        return await self.get_by_id(session_id)

    async def update_status(
        self,
        session_id: int,
        status: str,
        created_order_id: Optional[int] = None,
    ) -> CheckoutSession:
        values = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        if created_order_id is not None:
            values["created_order_id"] = created_order_id
        await self._db.execute(
            update(CheckoutSessionORM)
            .where(CheckoutSessionORM.id == session_id)
            .values(**values)
        )
        return await self.get_by_id(session_id)


class SQLPaymentRepository(PaymentRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_by_provider_payment_id(self, provider: str, provider_payment_id: str) -> Optional[Payment]:
        result = await self._db.execute(
            select(PaymentORM).where(
                PaymentORM.provider == provider,
                PaymentORM.provider_payment_id == provider_payment_id,
            )
        )
        payment = result.scalar_one_or_none()
        return _map_payment(payment) if payment else None

    async def get_by_checkout_session_id(self, checkout_session_id: int) -> list[Payment]:
        result = await self._db.execute(
            select(PaymentORM).where(PaymentORM.checkout_session_id == checkout_session_id)
        )
        return [_map_payment(payment) for payment in result.scalars().all()]

    async def upsert(self, payment: Payment) -> Payment:
        existing = None
        if payment.provider_payment_id:
            existing = await self.get_by_provider_payment_id(payment.provider, payment.provider_payment_id)

        now = datetime.now(UTC)
        if existing:
            await self._db.execute(
                update(PaymentORM)
                .where(PaymentORM.id == existing.id)
                .values(
                    checkout_session_id=payment.checkout_session_id or existing.checkout_session_id,
                    order_id=payment.order_id or existing.order_id,
                    provider_preference_id=payment.provider_preference_id,
                    status=payment.status,
                    provider_status=payment.provider_status,
                    amount=payment.amount,
                    currency=payment.currency,
                    raw_payload=payment.raw_payload,
                    approved_at=payment.approved_at or existing.approved_at,
                    updated_at=now,
                )
            )
            return await self.get_by_provider_payment_id(payment.provider, payment.provider_payment_id)

        orm = PaymentORM(
            checkout_session_id=payment.checkout_session_id,
            order_id=payment.order_id,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            provider_preference_id=payment.provider_preference_id,
            status=payment.status,
            provider_status=payment.provider_status,
            amount=payment.amount,
            currency=payment.currency,
            raw_payload=payment.raw_payload,
            approved_at=payment.approved_at,
            created_at=payment.created_at or now,
            updated_at=payment.updated_at or now,
        )
        self._db.add(orm)
        await self._db.flush()
        return _map_payment(orm)

    async def attach_order(self, payment_id: int, order_id: int) -> Payment:
        await self._db.execute(
            update(PaymentORM)
            .where(PaymentORM.id == payment_id)
            .values(order_id=order_id, updated_at=datetime.now(UTC))
        )
        result = await self._db.execute(select(PaymentORM).where(PaymentORM.id == payment_id))
        return _map_payment(result.scalar_one())


# ─── User Repository ──────────────────────────────────────────────────────────

class SQLUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self._db.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        u = result.scalar_one_or_none()
        if not u:
            return None
        return User(
            id=u.id, email=u.email, password_hash=u.password_hash,
            first_name=u.first_name, last_name=u.last_name, phone=u.phone,
            role=u.role, is_active=u.is_active, is_guest=u.is_guest,
            points_balance=u.points_balance, created_at=u.created_at,
        )

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(
            select(UserORM).where(UserORM.email == email)
        )
        u = result.scalar_one_or_none()
        if not u:
            return None
        return User(
            id=u.id, email=u.email, password_hash=u.password_hash,
            first_name=u.first_name, last_name=u.last_name, phone=u.phone,
            role=u.role, is_active=u.is_active, is_guest=u.is_guest,
            points_balance=u.points_balance, created_at=u.created_at,
        )

    async def create(self, user: User) -> User:
        orm = UserORM(
            email=user.email, password_hash=user.password_hash,
            first_name=user.first_name, last_name=user.last_name,
            phone=user.phone, role=user.role, is_active=user.is_active,
            is_guest=user.is_guest, points_balance=user.points_balance,
        )
        self._db.add(orm)
        await self._db.flush()
        return await self.get_by_id(orm.id)

    async def update(self, user: User) -> User:
        await self._db.execute(
            update(UserORM)
            .where(UserORM.id == user.id)
            .values(
                first_name=user.first_name,
                last_name=user.last_name,
                phone=user.phone,
            )
        )
        return await self.get_by_id(user.id)

    async def add_points(self, user_id: int, points: int) -> None:
        await self._db.execute(
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(points_balance=UserORM.points_balance + points)
        )


# ─── Address Repository ───────────────────────────────────────────────────────

class SQLAddressRepository(AddressRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_by_user(self, user_id: int) -> list[Address]:
        result = await self._db.execute(
            select(AddressORM).where(AddressORM.user_id == user_id)
        )
        return [self._map(a) for a in result.scalars().all()]

    async def get_by_id(self, address_id: int) -> Optional[Address]:
        result = await self._db.execute(
            select(AddressORM).where(AddressORM.id == address_id)
        )
        a = result.scalar_one_or_none()
        return self._map(a) if a else None

    async def create(self, address: Address) -> Address:
        orm = AddressORM(**{
            k: v for k, v in address.__dict__.items() if k != "id"
        })
        self._db.add(orm)
        await self._db.flush()
        return await self.get_by_id(orm.id)

    async def update(self, address: Address) -> Address:
        await self._db.execute(
            update(AddressORM).where(AddressORM.id == address.id).values(
                label=address.label, street=address.street,
                number=address.number, commune=address.commune,
                city=address.city, latitude=address.latitude,
                longitude=address.longitude, notes=address.notes,
            )
        )
        return await self.get_by_id(address.id)

    async def delete(self, address_id: int) -> None:
        from sqlalchemy import delete
        await self._db.execute(
            delete(AddressORM).where(AddressORM.id == address_id)
        )

    async def set_default(self, user_id: int, address_id: int) -> None:
        await self._db.execute(
            update(AddressORM)
            .where(AddressORM.user_id == user_id)
            .values(is_default=False)
        )
        await self._db.execute(
            update(AddressORM)
            .where(AddressORM.id == address_id)
            .values(is_default=True)
        )

    def _map(self, a) -> Address:
        return Address(
            id=a.id, user_id=a.user_id, label=a.label,
            street=a.street, number=a.number, commune=a.commune,
            city=a.city, latitude=a.latitude, longitude=a.longitude,
            notes=a.notes, is_default=a.is_default,
        )


# ─── Coupon Repository ────────────────────────────────────────────────────────

class SQLCouponRepository(CouponRepository):
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_by_code(self, code: str) -> Optional[Coupon]:
        result = await self._db.execute(
            select(CouponORM).where(CouponORM.code == code.upper())
        )
        c = result.scalar_one_or_none()
        if not c:
            return None
        return Coupon(
            id=c.id, code=c.code, discount_type=c.discount_type,
            discount_value=Decimal(c.discount_value),
            min_order_amount=Decimal(c.min_order_amount),
            max_uses=c.max_uses, uses_count=c.uses_count,
            user_id=c.user_id, expires_at=c.expires_at, is_active=c.is_active,
        )

    async def increment_uses(self, coupon_id: int) -> None:
        await self._db.execute(
            update(CouponORM)
            .where(CouponORM.id == coupon_id)
            .values(uses_count=CouponORM.uses_count + 1)
        )
