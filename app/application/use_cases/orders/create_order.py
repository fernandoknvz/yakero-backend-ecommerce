from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from ....domain.models.entities import Order
from ....domain.models.enums import OrderStatus, PaymentStatus
from ....domain.repositories.interfaces import (
    AddressRepository,
    CouponRepository,
    OrderRepository,
    ProductRepository,
    PromotionRepository,
    UserRepository,
)
from ...dtos.schemas import CreateOrderInput
from ..services.points_service import PointsService
from .pricing import OrderPricingService


POINTS_PER_PESO = Decimal("0.01")


class CreateOrderUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        user_repo: Optional[UserRepository],
        address_repo: Optional[AddressRepository],
        coupon_repo: Optional[CouponRepository],
        delivery_service,
        points_service: PointsService,
    ):
        self._orders = order_repo
        self._users = user_repo
        self._coupons = coupon_repo
        self._pricing = OrderPricingService(
            product_repo=product_repo,
            promotion_repo=promotion_repo,
            address_repo=address_repo,
            coupon_repo=coupon_repo,
            user_repo=user_repo,
            delivery_service=delivery_service,
        )
        self._points = points_service

    async def execute(
        self,
        data: CreateOrderInput,
        user_id: Optional[int] = None,
    ) -> Order:
        pricing = await self._pricing.preview(data, user_id=user_id)
        order = Order(
            id=None,
            user_id=user_id,
            guest_email=pricing.guest_email if not user_id else None,
            guest_phone=pricing.guest_phone if not user_id else None,
            address_id=pricing.address_id,
            delivery_type=pricing.delivery_type,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            subtotal=pricing.subtotal,
            delivery_fee=pricing.delivery_fee,
            discount=pricing.discount,
            points_used=pricing.points_to_use,
            total=pricing.total,
            mp_preference_id=None,
            mp_payment_id=None,
            mp_payment_status=None,
            notes=pricing.notes,
            items=[computed.order_item for computed in pricing.items],
            created_at=datetime.now(UTC),
            paid_at=None,
            ready_at=None,
            delivered_at=None,
            delivery_address_snapshot=pricing.delivery_address_snapshot,
        )

        saved = await self._orders.create(order)

        if user_id and pricing.points_to_use > 0:
            await self._users.add_points(user_id, -pricing.points_to_use)

        if data.coupon_code and self._coupons:
            coupon = await self._coupons.get_by_code(data.coupon_code)
            if coupon:
                await self._coupons.increment_uses(coupon.id)

        if user_id:
            earned = int(pricing.total * POINTS_PER_PESO)
            if earned > 0:
                await self._points.award_on_payment(user_id, saved.id, earned)

        return saved
