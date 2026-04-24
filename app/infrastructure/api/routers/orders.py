from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import (
    SQLAddressRepository,
    SQLCouponRepository,
    SQLOrderRepository,
    SQLProductRepository,
    SQLPromotionRepository,
    SQLUserRepository,
)
from ...database.session import get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import CreateOrderInput, OrderOut, OrderPreviewInput, OrderPreviewOut
from ....application.use_cases.orders.create_order import CreateOrderUseCase
from ....application.use_cases.orders.order_use_cases import GetOrderUseCase, GetUserOrdersUseCase
from ....application.use_cases.orders.pricing import OrderPricingService
from ....application.use_cases.services.delivery_service import DeliveryFeeService
from ....application.use_cases.services.points_service import PointsService
from ....auth import get_current_user, get_optional_user
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


router = APIRouter(prefix="/orders", tags=["Pedidos"])


def _build_pricing_service(db: AsyncSession) -> OrderPricingService:
    return OrderPricingService(
        product_repo=SQLProductRepository(db),
        promotion_repo=SQLPromotionRepository(db),
        address_repo=SQLAddressRepository(db),
        coupon_repo=SQLCouponRepository(db),
        user_repo=SQLUserRepository(db),
        delivery_service=DeliveryFeeService(),
    )


@router.post("/preview", response_model=OrderPreviewOut)
async def preview_order(
    data: OrderPreviewInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    try:
        pricing = await _build_pricing_service(db).preview(
            data,
            user_id=current_user.id if current_user else None,
        )
        return OrderPreviewOut(
            delivery_type=pricing.delivery_type,
            address_id=pricing.address_id,
            coupon_code=pricing.coupon_code,
            points_to_use=pricing.points_to_use,
            items=[
                {
                    "product_id": computed.order_item.product_id,
                    "promotion_id": computed.order_item.promotion_id,
                    "promotion_slot_id": computed.order_item.promotion_slot_id,
                    "product_name": computed.order_item.product_name,
                    "product_slug": computed.product_slug,
                    "quantity": computed.order_item.quantity,
                    "base_unit_price": computed.base_unit_price,
                    "modifiers_total": computed.modifiers_total,
                    "unit_price": computed.order_item.unit_price,
                    "total_price": computed.order_item.total_price,
                    "ticket_tag": computed.order_item.ticket_tag,
                    "notes": computed.order_item.notes,
                    "image_url": computed.image_url,
                    "selected_modifiers": [
                        {
                            "modifier_option_id": modifier.modifier_option_id,
                            "option_name": modifier.option_name,
                            "group_name": modifier.group_name,
                            "extra_price": modifier.extra_price,
                        }
                        for modifier in computed.order_item.modifiers
                    ],
                    "config_json": computed.order_item.config_json,
                }
                for computed in pricing.items
            ],
            subtotal=pricing.subtotal,
            delivery_fee=pricing.delivery_fee,
            discount=pricing.discount,
            pricing={
                "coupon_discount": pricing.coupon_discount,
                "points_discount": pricing.points_discount,
            },
            total=pricing.total,
            notes=pricing.notes,
        )
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.post("/", response_model=OrderOut, status_code=201)
async def create_order(
    data: CreateOrderInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    if not current_user and not data.guest_email:
        raise HTTPException(status_code=422, detail="Se requiere guest_email para pedidos sin cuenta.")

    user_repo = SQLUserRepository(db)
    order_repo = SQLOrderRepository(db)

    try:
        order = await CreateOrderUseCase(
            order_repo=order_repo,
            product_repo=SQLProductRepository(db),
            promotion_repo=SQLPromotionRepository(db),
            user_repo=user_repo,
            address_repo=SQLAddressRepository(db),
            coupon_repo=SQLCouponRepository(db),
            delivery_service=DeliveryFeeService(),
            points_service=PointsService(user_repo),
        ).execute(data, user_id=current_user.id if current_user else None)
        return order
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.get("/my", response_model=list[OrderOut])
async def my_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await GetUserOrdersUseCase(SQLOrderRepository(db)).execute(current_user.id, skip, limit)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    try:
        return await GetOrderUseCase(SQLOrderRepository(db)).execute(
            order_id,
            user_id=current_user.id if current_user else None,
        )
    except DomainError as exc:
        raise domain_error_to_http(exc)
