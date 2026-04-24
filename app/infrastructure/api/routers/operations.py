from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLCouponRepository
from ...database.session import get_db
from ....application.dtos.schemas import CouponOut, CouponValidateInput, DeliveryFeeInput, DeliveryFeeOut
from ....application.use_cases.orders.coupon_validation import CouponValidationService
from ....application.use_cases.services.delivery_service import DeliveryFeeService
from ....domain.exceptions import DomainError
from ..errors import domain_error_to_http


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
    try:
        repo = SQLCouponRepository(db)
        coupon = await CouponValidationService(repo).get_valid_coupon(
            code=data.code,
            subtotal=data.order_subtotal,
        )
        discount = await CouponValidationService(repo).calculate_discount(
            code=data.code,
            subtotal=data.order_subtotal,
        )
        return CouponOut(
            code=coupon.code,
            discount_type=coupon.discount_type,
            discount_value=coupon.discount_value,
            calculated_discount=discount,
        )
    except DomainError as exc:
        raise domain_error_to_http(exc)
