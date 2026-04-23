from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import OrderOut, PosOrderOut, PosStatusUpdateInput
from ....application.use_cases.orders.order_use_cases import UpdateOrderStatusUseCase
from ....auth import require_pos
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


router = APIRouter(prefix="/internal", tags=["POS Interno"])


@router.get("/orders/pending", response_model=list[PosOrderOut])
async def get_pending_orders(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_pos),
):
    orders = await SQLOrderRepository(db).get_pending_for_pos()
    result = []
    for order in orders:
        items_by_station = {
            tag.value: items
            for tag, items in order.items_by_ticket_tag().items()
        }
        result.append(
            PosOrderOut(
                id=order.id,
                status=order.status,
                delivery_type=order.delivery_type,
                created_at=order.created_at,
                notes=order.notes,
                items_by_station=items_by_station,
            )
        )
    return result


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def pos_update_status(
    order_id: int,
    data: PosStatusUpdateInput,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_pos),
):
    try:
        return await UpdateOrderStatusUseCase(SQLOrderRepository(db)).execute(order_id, data)
    except DomainError as exc:
        raise domain_error_to_http(exc)
