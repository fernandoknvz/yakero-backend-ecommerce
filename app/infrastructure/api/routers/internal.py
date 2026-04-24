import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.dev_seed import DEMO_COUPON_CODE, DEMO_USER_EMAIL, seed_dev_data
from ...database.models.orm_models import CategoryORM, CouponORM, ProductORM, UserORM
from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import AsyncSessionLocal, get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import OrderOut, PosOrderOut, PosStatusUpdateInput
from ....application.use_cases.orders.order_use_cases import UpdateOrderStatusUseCase
from ....auth import require_pos
from ....config import settings
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


@router.post("/bootstrap")
async def bootstrap_staging(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _ensure_bootstrap_allowed(x_internal_token)
    await _run_alembic_upgrade()
    seed_result = await _run_seed_and_collect()
    return {
        "migrations": "ok",
        "seed": "ok",
        "created": seed_result["created"],
        "existing": seed_result["existing"],
    }


def _ensure_bootstrap_allowed(x_internal_token: str | None) -> None:
    if settings.is_production and not settings.debug:
        raise HTTPException(status_code=403, detail="Bootstrap deshabilitado en produccion.")
    if not settings.internal_bootstrap_token:
        raise HTTPException(status_code=503, detail="INTERNAL_BOOTSTRAP_TOKEN no configurado.")
    if not x_internal_token or x_internal_token != settings.internal_bootstrap_token:
        raise HTTPException(status_code=401, detail="Token interno invalido.")


async def _run_alembic_upgrade() -> None:
    await asyncio.to_thread(_upgrade_head_sync)


def _upgrade_head_sync() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    alembic_ini = repo_root / "alembic.ini"
    config = AlembicConfig(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


async def _run_seed_and_collect() -> dict:
    async with AsyncSessionLocal() as session:
        before = await _seed_snapshot(session)
        await seed_dev_data(session)
        after = await _seed_snapshot(session)
        await session.commit()

    return {
        "created": {
            "categories": max(after["categories"] - before["categories"], 0),
            "products": max(after["products"] - before["products"], 0),
            "demo_user": (not before["demo_user"]) and after["demo_user"],
            "demo_coupon": (not before["demo_coupon"]) and after["demo_coupon"],
        },
        "existing": {
            "categories": min(before["categories"], after["categories"]),
            "products": min(before["products"], after["products"]),
            "demo_user": before["demo_user"],
            "demo_coupon": before["demo_coupon"],
        },
    }


async def _seed_snapshot(session: AsyncSession) -> dict:
    categories = await session.scalar(select(func.count()).select_from(CategoryORM))
    products = await session.scalar(select(func.count()).select_from(ProductORM))
    demo_user = await session.scalar(
        select(func.count()).select_from(UserORM).where(UserORM.email == DEMO_USER_EMAIL)
    )
    demo_coupon = await session.scalar(
        select(func.count()).select_from(CouponORM).where(CouponORM.code == DEMO_COUPON_CODE)
    )
    return {
        "categories": int(categories or 0),
        "products": int(products or 0),
        "demo_user": bool(demo_user),
        "demo_coupon": bool(demo_coupon),
    }
