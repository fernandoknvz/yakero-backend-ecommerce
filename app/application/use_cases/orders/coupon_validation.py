from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ....domain.exceptions import CouponError
from ....domain.repositories.interfaces import CouponRepository


class CouponValidationService:
    def __init__(self, coupon_repo: CouponRepository):
        self._coupons = coupon_repo

    async def calculate_discount(self, code: str, subtotal: Decimal) -> Decimal:
        coupon = await self.get_valid_coupon(code=code, subtotal=subtotal)
        if coupon.discount_type == "percent":
            return (subtotal * coupon.discount_value / 100).quantize(Decimal("1"))
        return min(coupon.discount_value, subtotal)

    async def get_valid_coupon(self, code: str, subtotal: Decimal):
        coupon = await self._coupons.get_by_code(code)
        if not coupon or not coupon.is_active:
            raise CouponError("Cupon invalido o expirado.")
        if coupon.expires_at and coupon.expires_at <= datetime.now(UTC):
            raise CouponError("Cupon invalido o expirado.")
        if coupon.max_uses and coupon.uses_count >= coupon.max_uses:
            raise CouponError("Este cupon ya no tiene usos disponibles.")
        if subtotal < coupon.min_order_amount:
            raise CouponError(
                f"El pedido minimo para este cupon es ${coupon.min_order_amount}."
            )
        return coupon
