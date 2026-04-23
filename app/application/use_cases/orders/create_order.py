from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from ....domain.models.entities import Order, OrderItem, OrderItemModifier
from ....domain.models.enums import OrderStatus, PaymentStatus, DeliveryType
from ....domain.repositories.interfaces import (
    OrderRepository, ProductRepository, PromotionRepository,
    UserRepository, AddressRepository, CouponRepository,
)
from ....domain.exceptions import (
    NotFoundError, ValidationError, ModifierValidationError,
    InsufficientPointsError, CouponError,
)
from ...dtos.schemas import CreateOrderInput, OrderItemInput
from ..services.delivery_service import DeliveryFeeService
from ..services.points_service import PointsService

POINTS_PER_PESO = Decimal("0.01")   # 1 punto por cada $100 CLP gastados
POINTS_VALUE    = Decimal("1.0")    # 1 punto = $1 CLP de descuento


class CreateOrderUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        user_repo: Optional[UserRepository],
        address_repo: Optional[AddressRepository],
        coupon_repo: Optional[CouponRepository],
        delivery_service: DeliveryFeeService,
        points_service: PointsService,
    ):
        self._orders = order_repo
        self._products = product_repo
        self._promotions = promotion_repo
        self._users = user_repo
        self._addresses = address_repo
        self._coupons = coupon_repo
        self._delivery = delivery_service
        self._points = points_service

    async def execute(
        self,
        data: CreateOrderInput,
        user_id: Optional[int] = None,
    ) -> Order:
        # ── 1. Construir ítems y calcular subtotal ──────────────────────────
        items, subtotal = await self._build_items(data.items)

        # ── 2. Costo de delivery ────────────────────────────────────────────
        delivery_fee = Decimal("0")
        address_snapshot = None
        if data.delivery_type == DeliveryType.DELIVERY:
            address = await self._addresses.get_by_id(data.address_id)
            if not address:
                raise NotFoundError("Dirección", data.address_id)
            if address.latitude and address.longitude:
                delivery_fee = await self._delivery.calculate(
                    address.latitude, address.longitude
                )
            address_snapshot = {
                "street": address.street,
                "number": address.number,
                "commune": address.commune,
                "city": address.city,
                "notes": address.notes,
            }

        # ── 3. Cupón de descuento ────────────────────────────────────────────
        discount = Decimal("0")
        if data.coupon_code:
            discount = await self._apply_coupon(data.coupon_code, subtotal)

        # ── 4. Puntos ────────────────────────────────────────────────────────
        points_discount = Decimal("0")
        points_used = 0
        if user_id and data.points_to_use > 0:
            user = await self._users.get_by_id(user_id)
            if user.points_balance < data.points_to_use:
                raise InsufficientPointsError(user.points_balance, data.points_to_use)
            points_used = data.points_to_use
            points_discount = Decimal(points_used) * POINTS_VALUE

        total_discount = discount + points_discount
        total = max(subtotal + delivery_fee - total_discount, Decimal("0"))

        # ── 5. Asignar order_id temporal a ítems (se actualiza tras persistir)
        order = Order(
            id=None,
            user_id=user_id,
            guest_email=data.guest_email if not user_id else None,
            guest_phone=data.guest_phone if not user_id else None,
            address_id=data.address_id,
            delivery_type=data.delivery_type,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            discount=total_discount,
            points_used=points_used,
            total=total,
            mp_preference_id=None,
            mp_payment_id=None,
            mp_payment_status=None,
            notes=data.notes,
            items=items,
            created_at=datetime.now(UTC),
            paid_at=None,
            ready_at=None,
            delivered_at=None,
            delivery_address_snapshot=address_snapshot,
        )

        saved = await self._orders.create(order)

        # ── 6. Post-persistencia: descontar puntos ───────────────────────────
        if user_id and points_used > 0:
            await self._users.add_points(user_id, -points_used)

        # ── 7. Acumular puntos por la compra ─────────────────────────────────
        if user_id:
            earned = int(total * POINTS_PER_PESO)
            if earned > 0:
                await self._points.award_on_payment(user_id, saved.id, earned)

        return saved

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _build_items(
        self, raw_items: list[OrderItemInput]
    ) -> tuple[list[OrderItem], Decimal]:
        items: list[OrderItem] = []
        subtotal = Decimal("0")

        for raw in raw_items:
            if raw.product_id:
                item, price = await self._build_product_item(raw)
            else:
                item, price = await self._build_promotion_item(raw)
            subtotal += price * raw.quantity
            items.append(item)

        return items, subtotal

    async def _build_product_item(
        self, raw: OrderItemInput
    ) -> tuple[OrderItem, Decimal]:
        product = await self._products.get_by_id(raw.product_id)
        if not product or not product.is_available:
            raise NotFoundError("Producto", raw.product_id)

        # Validar modificadores requeridos
        selected_ids = {m.modifier_option_id for m in raw.selected_modifiers}
        modifiers: list[OrderItemModifier] = []
        extra_total = Decimal("0")

        for group in product.modifier_groups:
            group_selections = [
                opt for opt in group.options if opt.id in selected_ids
            ]
            if group.is_required and len(group_selections) < group.min_selections:
                raise ModifierValidationError(group.name)
            if len(group_selections) > group.max_selections:
                raise ValidationError(
                    f"El grupo '{group.name}' permite máximo {group.max_selections} selecciones."
                )
            for opt in group_selections:
                extra_total += opt.extra_price
                modifiers.append(OrderItemModifier(
                    id=None,
                    order_item_id=0,  # se actualiza al persistir
                    modifier_option_id=opt.id,
                    option_name=opt.name,
                    group_name=group.name,
                    extra_price=opt.extra_price,
                ))

        unit_price = product.price + extra_total
        return (
            OrderItem(
                id=None,
                order_id=0,
                product_id=product.id,
                promotion_id=None,
                promotion_slot_id=None,
                product_name=product.name,
                quantity=raw.quantity,
                unit_price=unit_price,
                total_price=unit_price * raw.quantity,
                ticket_tag=product.ticket_tag,
                notes=raw.notes,
                config_json=None,
                modifiers=modifiers,
            ),
            unit_price,
        )

    async def _build_promotion_item(
        self, raw: OrderItemInput
    ) -> tuple[OrderItem, Decimal]:
        promo = await self._promotions.get_by_id(raw.promotion_id)
        if not promo or not promo.is_active:
            raise NotFoundError("Promoción", raw.promotion_id)

        slot = None
        if raw.promotion_slot_id:
            slot = next(
                (s for s in promo.slots if s.id == raw.promotion_slot_id), None
            )

        # Guardar configuración completa en config_json para el POS
        config_snapshot = {
            "promotion_name": promo.name,
            "slot_name": slot.slot_name if slot else None,
            "selected_modifiers": [
                {"modifier_option_id": m.modifier_option_id}
                for m in raw.selected_modifiers
            ],
        }

        ticket_tag = slot.ticket_tag if slot else promo.slots[0].ticket_tag if promo.slots else "caja"

        return (
            OrderItem(
                id=None,
                order_id=0,
                product_id=None,
                promotion_id=promo.id,
                promotion_slot_id=raw.promotion_slot_id,
                product_name=promo.name,
                quantity=raw.quantity,
                unit_price=promo.value,
                total_price=promo.value * raw.quantity,
                ticket_tag=ticket_tag,
                notes=raw.notes,
                config_json=config_snapshot,
                modifiers=[],
            ),
            promo.value,
        )

    async def _apply_coupon(self, code: str, subtotal: Decimal) -> Decimal:
        coupon = await self._coupons.get_by_code(code)
        if not coupon or not coupon.is_active:
            raise CouponError("Cupón inválido o expirado.")
        if coupon.max_uses and coupon.uses_count >= coupon.max_uses:
            raise CouponError("Este cupón ya no tiene usos disponibles.")
        if subtotal < coupon.min_order_amount:
            raise CouponError(
                f"El pedido mínimo para este cupón es ${coupon.min_order_amount}."
            )
        if coupon.discount_type == "percent":
            return (subtotal * coupon.discount_value / 100).quantize(Decimal("1"))
        return min(coupon.discount_value, subtotal)
