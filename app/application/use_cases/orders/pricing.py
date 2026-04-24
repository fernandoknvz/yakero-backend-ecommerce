from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from ....domain.exceptions import (
    InsufficientPointsError,
    InvalidModifierError,
    InvalidQuantityError,
    ModifierValidationError,
    NotFoundError,
    OrderPricingMismatchError,
    ProductUnavailableError,
    ValidationError,
)
from ....domain.models.entities import OrderItem, OrderItemModifier
from ....domain.models.enums import DeliveryType, TicketTag
from ....domain.repositories.interfaces import (
    AddressRepository,
    CouponRepository,
    ProductRepository,
    PromotionRepository,
    UserRepository,
)
from ...dtos.schemas import CreateOrderInput, OrderItemInput, OrderPreviewInput
from .coupon_validation import CouponValidationService


POINTS_VALUE = Decimal("1.0")


@dataclass
class ComputedOrderItem:
    order_item: OrderItem
    base_unit_price: Decimal
    modifiers_total: Decimal
    product_slug: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class OrderPricingResult:
    delivery_type: DeliveryType
    address_id: Optional[int]
    guest_email: Optional[str]
    guest_phone: Optional[str]
    coupon_code: Optional[str]
    notes: Optional[str]
    points_to_use: int
    subtotal: Decimal
    delivery_fee: Decimal
    coupon_discount: Decimal
    points_discount: Decimal
    discount: Decimal
    total: Decimal
    items: list[ComputedOrderItem] = field(default_factory=list)
    delivery_address_snapshot: Optional[dict] = None


class OrderPricingService:
    def __init__(
        self,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        address_repo: Optional[AddressRepository],
        coupon_repo: Optional[CouponRepository],
        user_repo: Optional[UserRepository],
        delivery_service,
    ):
        self._products = product_repo
        self._promotions = promotion_repo
        self._addresses = address_repo
        self._coupons = coupon_repo
        self._users = user_repo
        self._delivery = delivery_service

    async def preview(
        self,
        data: OrderPreviewInput | CreateOrderInput,
        user_id: Optional[int] = None,
    ) -> OrderPricingResult:
        computed_items, subtotal = await self._build_items(data.items)
        delivery_fee, snapshot = await self._build_delivery(data, user_id)
        coupon_discount = await self._apply_coupon(data.coupon_code, subtotal)
        points_discount = await self._apply_points(data.points_to_use, user_id)
        total_discount = coupon_discount + points_discount
        total = max(subtotal + delivery_fee - total_discount, Decimal("0"))

        pricing = OrderPricingResult(
            delivery_type=data.delivery_type,
            address_id=data.address_id,
            guest_email=str(data.guest_email) if data.guest_email else None,
            guest_phone=data.guest_phone,
            coupon_code=data.coupon_code,
            notes=getattr(data, "notes", None),
            points_to_use=data.points_to_use,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            coupon_discount=coupon_discount,
            points_discount=points_discount,
            discount=total_discount,
            total=total,
            items=computed_items,
            delivery_address_snapshot=snapshot,
        )
        self._validate_client_totals(data, pricing)
        return pricing

    async def _build_items(
        self,
        raw_items: list[OrderItemInput],
    ) -> tuple[list[ComputedOrderItem], Decimal]:
        items: list[ComputedOrderItem] = []
        subtotal = Decimal("0")

        for raw in raw_items:
            if raw.quantity <= 0:
                raise InvalidQuantityError()
            computed = (
                await self._build_product_item(raw)
                if raw.product_id
                else await self._build_promotion_item(raw)
            )
            subtotal += computed.order_item.total_price
            items.append(computed)

        return items, subtotal

    async def _build_product_item(self, raw: OrderItemInput) -> ComputedOrderItem:
        product = await self._products.get_by_id(raw.product_id)
        if not product:
            raise NotFoundError("Producto", raw.product_id)
        if not product.is_available:
            raise ProductUnavailableError(raw.product_id)

        selected_ids = [selection.modifier_option_id for selection in raw.selected_modifiers]
        valid_options = {
            option.id: (group, option)
            for group in product.modifier_groups
            for option in group.options
        }

        for option_id in selected_ids:
            group_option = valid_options.get(option_id)
            if not group_option:
                raise InvalidModifierError(product.id, option_id)
            if not group_option[1].is_available:
                raise ValidationError(
                    f"El modificador '{group_option[1].name}' no esta disponible."
                )

        modifiers: list[OrderItemModifier] = []
        modifiers_total = Decimal("0")

        for group in product.modifier_groups:
            group_selections = [
                valid_options[option_id][1]
                for option_id in selected_ids
                if option_id in valid_options and valid_options[option_id][0].id == group.id
            ]
            if group.is_required and len(group_selections) < group.min_selections:
                raise ModifierValidationError(group.name)
            if (
                not group.is_required
                and group_selections
                and len(group_selections) < group.min_selections
            ):
                raise ValidationError(
                    f"El grupo '{group.name}' requiere al menos {group.min_selections} selecciones."
                )
            if len(group_selections) > group.max_selections:
                raise ValidationError(
                    f"El grupo '{group.name}' permite maximo {group.max_selections} selecciones."
                )
            for option in group_selections:
                modifiers_total += option.extra_price
                modifiers.append(
                    OrderItemModifier(
                        id=None,
                        order_item_id=0,
                        modifier_option_id=option.id,
                        option_name=option.name,
                        group_name=group.name,
                        extra_price=option.extra_price,
                    )
                )

        unit_price = product.price + modifiers_total
        return ComputedOrderItem(
            order_item=OrderItem(
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
                config_json={
                    "product_slug": product.slug,
                    "selected_modifier_option_ids": selected_ids,
                    "priced_at": datetime.now(UTC).isoformat(),
                },
                modifiers=modifiers,
            ),
            base_unit_price=product.price,
            modifiers_total=modifiers_total,
            product_slug=product.slug,
            image_url=product.image_url,
        )

    async def _build_promotion_item(self, raw: OrderItemInput) -> ComputedOrderItem:
        promo = await self._promotions.get_by_id(raw.promotion_id)
        if not promo:
            raise NotFoundError("Promocion", raw.promotion_id)
        if not promo.is_active:
            raise ValidationError("La promocion solicitada no esta disponible.")

        slot = None
        if raw.promotion_slot_id is not None:
            slot = next((candidate for candidate in promo.slots if candidate.id == raw.promotion_slot_id), None)
            if slot is None:
                raise ValidationError("La configuracion de promocion solicitada no es valida.")

        config_snapshot = {
            "promotion_name": promo.name,
            "slot_name": slot.slot_name if slot else None,
            "selected_modifiers": [
                {"modifier_option_id": selection.modifier_option_id}
                for selection in raw.selected_modifiers
            ],
        }
        ticket_tag = (
            slot.ticket_tag
            if slot
            else promo.slots[0].ticket_tag
            if promo.slots
            else TicketTag.CAJA
        )
        unit_price = promo.value

        return ComputedOrderItem(
            order_item=OrderItem(
                id=None,
                order_id=0,
                product_id=None,
                promotion_id=promo.id,
                promotion_slot_id=raw.promotion_slot_id,
                product_name=promo.name,
                quantity=raw.quantity,
                unit_price=unit_price,
                total_price=unit_price * raw.quantity,
                ticket_tag=ticket_tag,
                notes=raw.notes,
                config_json=config_snapshot,
                modifiers=[],
            ),
            base_unit_price=unit_price,
            modifiers_total=Decimal("0"),
            product_slug=None,
            image_url=promo.image_url,
        )

    async def _build_delivery(
        self,
        data: OrderPreviewInput | CreateOrderInput,
        user_id: Optional[int],
    ) -> tuple[Decimal, Optional[dict]]:
        if data.delivery_type != DeliveryType.DELIVERY:
            return Decimal("0"), None
        if not self._addresses:
            raise ValidationError("No hay repositorio de direcciones configurado.")

        address = await self._addresses.get_by_id(data.address_id)
        if not address:
            raise NotFoundError("Direccion", data.address_id)
        if user_id is not None and address.user_id not in (None, user_id):
            raise ValidationError("La direccion seleccionada no pertenece al usuario autenticado.")
        if user_id is None and address.user_id is not None:
            raise ValidationError("El checkout invitado no puede reutilizar direcciones guardadas.")

        delivery_fee = Decimal("0")
        if address.latitude is not None and address.longitude is not None:
            delivery_fee = await self._delivery.calculate(address.latitude, address.longitude)

        snapshot = {
            "label": address.label,
            "street": address.street,
            "number": address.number,
            "commune": address.commune,
            "city": address.city,
            "notes": address.notes,
        }
        return delivery_fee, snapshot

    async def _apply_coupon(self, code: Optional[str], subtotal: Decimal) -> Decimal:
        if not code:
            return Decimal("0")
        if not self._coupons:
            raise ValidationError("No hay repositorio de cupones configurado.")
        return await CouponValidationService(self._coupons).calculate_discount(code, subtotal)

    async def _apply_points(self, points_to_use: int, user_id: Optional[int]) -> Decimal:
        if points_to_use <= 0:
            return Decimal("0")
        if user_id is None:
            raise ValidationError("Solo un usuario autenticado puede usar puntos.")
        if not self._users:
            raise ValidationError("No hay repositorio de usuarios configurado.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("Usuario", user_id)
        if user.points_balance < points_to_use:
            raise InsufficientPointsError(user.points_balance, points_to_use)
        return Decimal(points_to_use) * POINTS_VALUE

    def _validate_client_totals(
        self,
        data: OrderPreviewInput | CreateOrderInput,
        pricing: OrderPricingResult,
    ) -> None:
        if not data.client_totals:
            return

        expected = {
            "subtotal": pricing.subtotal,
            "delivery_fee": pricing.delivery_fee,
            "discount": pricing.discount,
            "total": pricing.total,
        }
        for field, calculated in expected.items():
            client_value = getattr(data.client_totals, field)
            if client_value is not None and client_value != calculated:
                raise OrderPricingMismatchError(field)
