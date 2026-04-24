from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from ...domain.models.enums import (
    DeliveryType,
    ModifierType,
    OrderStatus,
    PaymentStatus,
    TicketTag,
    UserRole,
)


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("La contrasena debe tener al menos 8 caracteres")
        return value


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: UserRole


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


class ProductCategoryRefOut(BaseModel):
    id: int
    name: str
    slug: str
    ticket_tag: TicketTag
    image_url: Optional[str] = None
    sort_order: int

    model_config = {"from_attributes": True}


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


class ProductFlagsOut(BaseModel):
    is_configurable: bool
    has_required_modifiers: bool
    has_optional_modifiers: bool
    has_image: bool


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
    category: Optional[ProductCategoryRefOut] = None
    flags: Optional[ProductFlagsOut] = None

    model_config = {"from_attributes": True}


class ProductListItemOut(BaseModel):
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
    category: ProductCategoryRefOut
    flags: ProductFlagsOut


class ProductDetailOut(ProductListItemOut):
    modifier_groups: list[ModifierGroupOut]
    applicable_promotions: list["PromotionSummaryOut"] = Field(default_factory=list)


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    ticket_tag: TicketTag
    image_url: Optional[str]
    sort_order: int
    products: list[ProductOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CategorySummaryOut(BaseModel):
    id: int
    name: str
    slug: str
    ticket_tag: TicketTag
    image_url: Optional[str]
    sort_order: int


class PromotionSlotOut(BaseModel):
    id: int
    slot_name: str
    pieces: int
    ticket_tag: TicketTag
    modifier_groups: list[ModifierGroupOut]

    model_config = {"from_attributes": True}


class PromotionSummaryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    promotion_type: str
    value: Decimal
    image_url: Optional[str]


class PromotionOut(PromotionSummaryOut):
    slots: list[PromotionSlotOut]

    model_config = {"from_attributes": True}


class CouponValidateInput(BaseModel):
    code: str
    order_subtotal: Decimal


class CouponOut(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    calculated_discount: Decimal


class OrderItemModifierInput(BaseModel):
    modifier_option_id: int


class ClientTotalsInput(BaseModel):
    subtotal: Optional[Decimal] = None
    delivery_fee: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    total: Optional[Decimal] = None


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
            raise ValueError("Cada item debe tener product_id o promotion_id")
        return self


class OrderPricingInput(BaseModel):
    delivery_type: DeliveryType
    address_id: Optional[int] = None
    guest_email: Optional[EmailStr] = None
    guest_phone: Optional[str] = None
    items: list[OrderItemInput] = Field(min_length=1)
    coupon_code: Optional[str] = None
    points_to_use: int = Field(default=0, ge=0)
    client_totals: Optional[ClientTotalsInput] = None

    @model_validator(mode="after")
    def validate_delivery_address(self) -> "OrderPricingInput":
        if self.delivery_type == DeliveryType.DELIVERY and not self.address_id:
            raise ValueError("Se requiere address_id para delivery")
        return self


class OrderPreviewInput(OrderPricingInput):
    notes: Optional[str] = None


class CreateOrderInput(OrderPricingInput):
    notes: Optional[str] = None


class SelectedModifierOut(BaseModel):
    modifier_option_id: Optional[int]
    option_name: str
    group_name: str
    extra_price: Decimal


class PricingBreakdownOut(BaseModel):
    coupon_discount: Decimal
    points_discount: Decimal


class OrderPreviewItemOut(BaseModel):
    product_id: Optional[int]
    promotion_id: Optional[int]
    promotion_slot_id: Optional[int]
    product_name: str
    product_slug: Optional[str] = None
    quantity: int
    base_unit_price: Decimal
    modifiers_total: Decimal
    unit_price: Decimal
    total_price: Decimal
    ticket_tag: TicketTag
    notes: Optional[str] = None
    image_url: Optional[str] = None
    selected_modifiers: list[SelectedModifierOut] = Field(default_factory=list)
    config_json: Optional[dict[str, Any]] = None


class OrderPreviewOut(BaseModel):
    delivery_type: DeliveryType
    address_id: Optional[int] = None
    coupon_code: Optional[str] = None
    points_to_use: int
    items: list[OrderPreviewItemOut]
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    pricing: PricingBreakdownOut
    total: Decimal
    notes: Optional[str] = None


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
    payment_provider: Optional[str] = None
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
    mp_payment_id: Optional[str] = None

    model_config = {"from_attributes": True}


class CreatePaymentPreferenceInput(BaseModel):
    order_id: int = Field(ge=1)


class CreatePaymentPreferenceOut(BaseModel):
    preference_id: str
    init_point: Optional[str] = None
    sandbox_init_point: Optional[str] = None
    order_id: int


class PosStatusUpdateInput(BaseModel):
    status: OrderStatus
    pos_order_ref: Optional[str] = None


class PosOrderOut(BaseModel):
    id: int
    status: OrderStatus
    delivery_type: DeliveryType
    created_at: datetime
    notes: Optional[str]
    items_by_station: dict[str, list[OrderItemOut]]

    model_config = {"from_attributes": True}


class DeliveryFeeInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeliveryFeeOut(BaseModel):
    distance_km: float
    fee: Decimal
    is_available: bool


ProductDetailOut.model_rebuild()
