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
from ...payment.mercadopago_service import MercadoPagoService
from ..errors import domain_error_to_http
from ....application.dtos.schemas import CreateOrderInput, OrderOut
from ....application.use_cases.orders.create_order import CreateOrderUseCase
from ....application.use_cases.orders.order_use_cases import GetOrderUseCase, GetUserOrdersUseCase
from ....application.use_cases.services.delivery_service import DeliveryFeeService
from ....application.use_cases.services.points_service import PointsService
from ....auth import get_current_user, get_optional_user
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


router = APIRouter(prefix="/orders", tags=["Pedidos"])


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

        pref_id = await MercadoPagoService().create_preference(order, back_urls={})
        await order_repo.update_mp_preference(order.id, pref_id)
        order.mp_preference_id = pref_id
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
