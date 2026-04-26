from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Numeric,
    ForeignKey, Text, Float, JSON, Enum as SAEnum, MetaData,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, DeclarativeBase
from ....domain.models.enums import (
    OrderStatus, PaymentStatus, DeliveryType, TicketTag, UserRole, ModifierType,
)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    pass


def enum_values(enum_cls):
    return [member.value for member in enum_cls]


class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(30))
    role = Column(
        SAEnum(UserRole, values_callable=enum_values),
        default=UserRole.CUSTOMER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True)
    is_guest = Column(Boolean, default=False)
    points_balance = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    addresses = relationship("AddressORM", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("OrderORM", back_populates="user")


class AddressORM(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    label = Column(String(100), nullable=False)
    street = Column(String(200), nullable=False)
    number = Column(String(20), nullable=False)
    commune = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    notes = Column(Text)
    is_default = Column(Boolean, default=False)

    user = relationship("UserORM", back_populates="addresses")


class CategoryORM(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(120), unique=True, nullable=False)
    ticket_tag = Column(SAEnum(TicketTag, values_callable=enum_values), nullable=False)
    image_url = Column(String(500))
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    products = relationship("ProductORM", back_populates="category")


class ProductORM(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    sku = Column(String(50), unique=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 0), nullable=False)
    image_url = Column(String(500))
    ticket_tag = Column(SAEnum(TicketTag, values_callable=enum_values), nullable=False)
    is_available = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    category = relationship("CategoryORM", back_populates="products")
    modifier_groups = relationship(
        "ModifierGroupORM", back_populates="product", cascade="all, delete-orphan"
    )


class ModifierGroupORM(Base):
    __tablename__ = "modifier_groups"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    promotion_slot_id = Column(Integer, ForeignKey("promotion_slots.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(100), nullable=False)
    modifier_type = Column(
        SAEnum(ModifierType, values_callable=enum_values),
        default=ModifierType.SINGLE,
        nullable=False,
    )
    min_selections = Column(Integer, default=1)
    max_selections = Column(Integer, default=1)
    is_required = Column(Boolean, default=True)

    product = relationship("ProductORM", back_populates="modifier_groups")
    promotion_slot = relationship("PromotionSlotORM", back_populates="modifier_groups")
    options = relationship(
        "ModifierOptionORM", back_populates="group", cascade="all, delete-orphan"
    )


class ModifierOptionORM(Base):
    __tablename__ = "modifier_options"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    extra_price = Column(Numeric(10, 0), default=0, nullable=False)
    is_available = Column(Boolean, default=True)

    group = relationship("ModifierGroupORM", back_populates="options")


class PromotionORM(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    promotion_type = Column(String(50), nullable=False)
    value = Column(Numeric(10, 0), nullable=False)
    image_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    starts_at = Column(DateTime)
    ends_at = Column(DateTime)

    slots = relationship(
        "PromotionSlotORM", back_populates="promotion", cascade="all, delete-orphan"
    )


class PromotionSlotORM(Base):
    __tablename__ = "promotion_slots"

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)
    slot_name = Column(String(200), nullable=False)
    pieces = Column(Integer, nullable=False)
    ticket_tag = Column(SAEnum(TicketTag, values_callable=enum_values), nullable=False)

    promotion = relationship("PromotionORM", back_populates="slots")
    modifier_groups = relationship(
        "ModifierGroupORM", back_populates="promotion_slot", cascade="all, delete-orphan"
    )


class CouponORM(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    discount_type = Column(String(20), nullable=False)   # "fixed" | "percent"
    discount_value = Column(Numeric(10, 2), nullable=False)
    min_order_amount = Column(Numeric(10, 0), default=0)
    max_uses = Column(Integer)
    uses_count = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)


class OrderORM(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    guest_email = Column(String(255))
    guest_phone = Column(String(30))
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    delivery_type = Column(
        SAEnum(DeliveryType, values_callable=enum_values),
        nullable=False,
    )
    status = Column(
        SAEnum(OrderStatus, values_callable=enum_values),
        default=OrderStatus.PENDING,
        nullable=False,
    )
    payment_status = Column(
        SAEnum(PaymentStatus, values_callable=enum_values),
        default=PaymentStatus.PENDING,
        nullable=False,
    )

    subtotal = Column(Numeric(10, 0), nullable=False)
    delivery_fee = Column(Numeric(10, 0), default=0)
    discount = Column(Numeric(10, 0), default=0)
    points_used = Column(Integer, default=0)
    total = Column(Numeric(10, 0), nullable=False)

    payment_provider = Column(String(50))
    mp_preference_id = Column(String(255), index=True)
    mp_payment_id = Column(String(255), index=True)
    mp_payment_status = Column(String(50))

    notes = Column(Text)
    delivery_address_snapshot = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    ready_at = Column(DateTime)
    delivered_at = Column(DateTime)

    user = relationship("UserORM", back_populates="orders")
    items = relationship(
        "OrderItemORM", back_populates="order", cascade="all, delete-orphan"
    )


class CheckoutSessionORM(Base):
    __tablename__ = "checkout_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    guest_email = Column(String(255))
    guest_phone = Column(String(30))
    address_id = Column(Integer, nullable=True)
    delivery_type = Column(String(20), nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    payment_provider = Column(String(50), default="mercadopago", nullable=False)
    mp_preference_id = Column(String(255), index=True)
    mp_init_point = Column(Text)
    mp_sandbox_init_point = Column(Text)
    cart_snapshot = Column(JSON, nullable=False)
    customer_data = Column(JSON)
    pricing_snapshot = Column(JSON)
    delivery_address_snapshot = Column(JSON)
    coupon_code = Column(String(50))
    subtotal = Column(Numeric(10, 0), nullable=False)
    delivery_fee = Column(Numeric(10, 0), default=0, nullable=False)
    discount = Column(Numeric(10, 0), default=0, nullable=False)
    points_used = Column(Integer, default=0, nullable=False)
    total = Column(Numeric(10, 0), nullable=False)
    created_order_id = Column(Integer, nullable=True, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PaymentORM(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_provider_payment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    checkout_session_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)
    provider = Column(String(50), nullable=False)
    provider_payment_id = Column(String(255))
    provider_preference_id = Column(String(255), index=True)
    status = Column(String(50), nullable=False, index=True)
    provider_status = Column(String(50))
    amount = Column(Numeric(10, 0))
    currency = Column(String(3), default="CLP", nullable=False)
    raw_payload = Column(JSON)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class OrderItemORM(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=True)
    promotion_slot_id = Column(Integer, ForeignKey("promotion_slots.id"), nullable=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Numeric(10, 0), nullable=False)
    total_price = Column(Numeric(10, 0), nullable=False)
    ticket_tag = Column(SAEnum(TicketTag, values_callable=enum_values), nullable=False)
    notes = Column(Text)
    config_json = Column(JSON)

    order = relationship("OrderORM", back_populates="items")
    modifiers = relationship(
        "OrderItemModifierORM",
        back_populates="order_item",
        cascade="all, delete-orphan",
    )


class OrderItemModifierORM(Base):
    __tablename__ = "order_item_modifiers"

    id = Column(Integer, primary_key=True, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False)
    modifier_option_id = Column(Integer, ForeignKey("modifier_options.id"), nullable=True)
    option_name = Column(String(100), nullable=False)
    group_name = Column(String(100), nullable=False)
    extra_price = Column(Numeric(10, 0), default=0)

    order_item = relationship("OrderItemORM", back_populates="modifiers")
