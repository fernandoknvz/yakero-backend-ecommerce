from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLCouponRepository
from ...database.session import get_db
from ....application.dtos.schemas import CouponOut, CouponValidateInput, DeliveryFeeInput, DeliveryFeeOut
from ....application.use_cases.services.delivery_service import DeliveryFeeService


delivery_router = APIRouter(prefix="/delivery", tags=["Delivery"])
coupons_router = APIRouter(prefix="/coupons", tags=["Cupones"])


@delivery_router.post("/fee", response_model=DeliveryFeeOut)
async def calculate_delivery_fee(data: DeliveryFeeInput):
    distance, fee, available = await DeliveryFeeService().get_info(data.latitude, data.longitude)
    return DeliveryFeeOut(distance_km=distance, fee=fee, is_available=available)


@coupons_router.post("/validate", response_model=CouponOut)
async def validate_coupon(
    data: CouponValidateInput,
    db: AsyncSession = Depends(get_db),
):
    coupon = await SQLCouponRepository(db).get_by_code(data.code)
    if not coupon or not coupon.is_active:
        raise HTTPException(status_code=400, detail="Cupon invalido o expirado")
    if coupon.max_uses and coupon.uses_count >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="Cupon sin usos disponibles")
    if data.order_subtotal < coupon.min_order_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Monto minimo para este cupon: ${coupon.min_order_amount}",
        )

    if coupon.discount_type == "percent":
        discount = (data.order_subtotal * coupon.discount_value / 100).quantize(Decimal("1"))
    else:
        discount = min(coupon.discount_value, data.order_subtotal)

    return CouponOut(
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        calculated_discount=discount,
    )
