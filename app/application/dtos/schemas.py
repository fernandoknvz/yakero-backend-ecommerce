from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from ...domain.models.enums import (
    OrderStatus, PaymentStatus, DeliveryType, TicketTag,
    UserRole, ModifierType,
)


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: UserRole


# ─── Users ───────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    role: UserRole
    points_balance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateInput(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


# ─── Address ─────────────────────────────────────────────────────────────────

class AddressInput(BaseModel):
    label: str
    street: str
    number: str
    commune: str
    city: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    is_default: bool = False


class AddressOut(BaseModel):
    id: int
    label: str
    street: str
    number: str
    commune: str
    city: str
    latitude: Optional[float]
    longitude: Optional[float]
    notes: Optional[str]
    is_default: bool

    model_config = {"from_attributes": True}


# ─── Products ────────────────────────────────────────────────────────────────

class ModifierOptionOut(BaseModel):
    id: int
    name: str
    extra_price: Decimal
    is_available: bool

    model_config = {"from_attributes": True}


class ModifierGroupOut(BaseModel):
    id: int
    name: str
    modifier_type: ModifierType
    min_selections: int
    max_selections: int
    is_required: bool
    options: list[ModifierOptionOut]

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    category_id: int
    sku: Optional[str]
    name: str
    slug: str
    description: Optional[str]
    price: Decimal
    image_url: Optional[str]
    ticket_tag: TicketTag
    is_available: bool
    modifier_groups: list[ModifierGroupOut]

    model_config = {"from_attributes": True}


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    ticket_tag: TicketTag
    image_url: Optional[str]
    sort_order: int
    products: list[ProductOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ─── Promotions ──────────────────────────────────────────────────────────────

class PromotionSlotOut(BaseModel):
    id: int
    slot_name: str
    pieces: int
    ticket_tag: TicketTag
    modifier_groups: list[ModifierGroupOut]

    model_config = {"from_attributes": True}


class PromotionOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    promotion_type: str
    value: Decimal
    image_url: Optional[str]
    slots: list[PromotionSlotOut]

    model_config = {"from_attributes": True}


# ─── Coupons ─────────────────────────────────────────────────────────────────

class CouponValidateInput(BaseModel):
    code: str
    order_subtotal: Decimal


class CouponOut(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    calculated_discount: Decimal


# ─── Orders ──────────────────────────────────────────────────────────────────

class OrderItemModifierInput(BaseModel):
    modifier_option_id: int


class OrderItemInput(BaseModel):
    product_id: Optional[int] = None
    promotion_id: Optional[int] = None
    promotion_slot_id: Optional[int] = None
    quantity: int = Field(default=1, ge=1, le=99)
    notes: Optional[str] = None
    selected_modifiers: list[OrderItemModifierInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def product_or_promotion(self) -> "OrderItemInput":
        if not self.product_id and not self.promotion_id:
            raise ValueError("Cada ítem debe tener product_id o promotion_id")
        return self


class CreateOrderInput(BaseModel):
    delivery_type: DeliveryType
    address_id: Optional[int] = None         # requerido si delivery
    guest_email: Optional[EmailStr] = None   # requerido si guest
    guest_phone: Optional[str] = None
    items: list[OrderItemInput] = Field(min_length=1)
    notes: Optional[str] = None
    coupon_code: Optional[str] = None
    points_to_use: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_delivery_address(self) -> "CreateOrderInput":
        if self.delivery_type == DeliveryType.DELIVERY and not self.address_id:
            raise ValueError("Se requiere address_id para delivery")
        return self


class OrderItemModifierOut(BaseModel):
    option_name: str
    group_name: str
    extra_price: Decimal

    model_config = {"from_attributes": True}


class OrderItemOut(BaseModel):
    id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    ticket_tag: TicketTag
    notes: Optional[str]
    modifiers: list[OrderItemModifierOut]

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    delivery_type: DeliveryType
    status: OrderStatus
    payment_status: PaymentStatus
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    notes: Optional[str]
    items: list[OrderItemOut]
    created_at: datetime
    paid_at: Optional[datetime]
    ready_at: Optional[datetime]
    delivered_at: Optional[datetime]
    mp_preference_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── POS Internal ────────────────────────────────────────────────────────────

class PosStatusUpdateInput(BaseModel):
    """Payload que el POS envía para actualizar estado de un pedido."""
    status: OrderStatus
    pos_order_ref: Optional[str] = None  # referencia interna del POS


class PosOrderOut(BaseModel):
    """Estructura enriquecida que el POS consume para generar comandas."""
    id: int
    status: OrderStatus
    delivery_type: DeliveryType
    created_at: datetime
    notes: Optional[str]
    items_by_station: dict[str, list[OrderItemOut]]  # key = ticket_tag

    model_config = {"from_attributes": True}


# ─── Delivery fee ────────────────────────────────────────────────────────────

class DeliveryFeeInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeliveryFeeOut(BaseModel):
    distance_km: float
    fee: Decimal
    is_available: bool
