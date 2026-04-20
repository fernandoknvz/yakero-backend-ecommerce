from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from .enums import OrderStatus, PaymentStatus, DeliveryType, TicketTag, UserRole


@dataclass
class User:
    id: Optional[int]
    email: str
    password_hash: str
    first_name: str
    last_name: str
    phone: Optional[str]
    role: UserRole
    is_active: bool
    is_guest: bool
    points_balance: int
    created_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class Address:
    id: Optional[int]
    user_id: Optional[int]
    label: str
    street: str
    number: str
    commune: str
    city: str
    latitude: Optional[float]
    longitude: Optional[float]
    notes: Optional[str]
    is_default: bool


@dataclass
class Category:
    id: Optional[int]
    name: str
    slug: str
    ticket_tag: TicketTag
    image_url: Optional[str]
    sort_order: int
    is_active: bool


@dataclass
class ModifierOption:
    id: Optional[int]
    group_id: int
    name: str
    extra_price: Decimal
    is_available: bool


@dataclass
class ModifierGroup:
    id: Optional[int]
    product_id: int
    name: str
    modifier_type: str
    min_selections: int
    max_selections: int
    is_required: bool
    options: list[ModifierOption] = field(default_factory=list)


@dataclass
class Product:
    id: Optional[int]
    category_id: int
    sku: Optional[str]
    name: str
    slug: str
    description: Optional[str]
    price: Decimal
    image_url: Optional[str]
    ticket_tag: TicketTag
    is_available: bool
    sort_order: int
    modifier_groups: list[ModifierGroup] = field(default_factory=list)


@dataclass
class PromotionSlot:
    """Un slot dentro de un bundle (ej: 'Roll 1 de 10 piezas tipo Furay')"""
    id: Optional[int]
    promotion_id: int
    slot_name: str           # "Roll Furay 10pz"
    pieces: int              # 10
    ticket_tag: TicketTag
    modifier_groups: list[ModifierGroup] = field(default_factory=list)


@dataclass
class Promotion:
    id: Optional[int]
    name: str
    description: Optional[str]
    promotion_type: str
    value: Decimal           # precio total si bundle, descuento si discount
    image_url: Optional[str]
    is_active: bool
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    slots: list[PromotionSlot] = field(default_factory=list)


@dataclass
class Coupon:
    id: Optional[int]
    code: str
    discount_type: str       # "fixed" | "percent"
    discount_value: Decimal
    min_order_amount: Decimal
    max_uses: Optional[int]
    uses_count: int
    user_id: Optional[int]   # None = público
    expires_at: Optional[datetime]
    is_active: bool


@dataclass
class OrderItemModifier:
    id: Optional[int]
    order_item_id: int
    modifier_option_id: int
    option_name: str
    group_name: str
    extra_price: Decimal


@dataclass
class OrderItem:
    id: Optional[int]
    order_id: int
    product_id: Optional[int]
    promotion_id: Optional[int]
    promotion_slot_id: Optional[int]
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    ticket_tag: TicketTag
    notes: Optional[str]
    config_json: Optional[dict]   # configuración snapshot para POS
    modifiers: list[OrderItemModifier] = field(default_factory=list)


@dataclass
class Order:
    id: Optional[int]
    user_id: Optional[int]       # None si guest
    guest_email: Optional[str]
    guest_phone: Optional[str]
    address_id: Optional[int]
    delivery_type: DeliveryType
    status: OrderStatus
    payment_status: PaymentStatus

    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    points_used: int
    total: Decimal

    mp_preference_id: Optional[str]
    mp_payment_id: Optional[str]
    mp_payment_status: Optional[str]

    notes: Optional[str]
    items: list[OrderItem] = field(default_factory=list)

    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    # snapshot de dirección (para historial inmutable)
    delivery_address_snapshot: Optional[dict] = None

    def can_transition_to(self, new_status: OrderStatus) -> bool:
        valid_transitions = {
            OrderStatus.PENDING: [OrderStatus.PAID, OrderStatus.CANCELLED],
            OrderStatus.PAID: [OrderStatus.PREPARING, OrderStatus.CANCELLED],
            OrderStatus.PREPARING: [OrderStatus.READY, OrderStatus.VOIDED],
            OrderStatus.READY: [OrderStatus.DISPATCHED, OrderStatus.DELIVERED],
            OrderStatus.DISPATCHED: [OrderStatus.DELIVERED],
            OrderStatus.DELIVERED: [],
            OrderStatus.CANCELLED: [],
            OrderStatus.VOIDED: [],
        }
        return new_status in valid_transitions.get(self.status, [])

    def items_by_ticket_tag(self) -> dict[TicketTag, list[OrderItem]]:
        """Agrupa ítems por estación de cocina — útil para impresión de comandas."""
        result: dict[TicketTag, list[OrderItem]] = {}
        for item in self.items:
            result.setdefault(item.ticket_tag, []).append(item)
        return result
