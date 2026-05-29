import asyncio
import logging
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.dev_seed import DEMO_COUPON_CODE, DEMO_USER_EMAIL, seed_dev_data
from ...database.connection import build_async_engine_config
from ...database.models.orm_models import CategoryORM, CouponORM, ProductORM, UserORM
from ...database.pos_catalog_audit import PosCatalogAuditService
from ...database.pos_catalog_sync import PosCatalogSyncService
from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import AsyncSessionLocal, get_db
from ...clients import PosClientError
from ..errors import domain_error_to_http
from ....application.dtos.schemas import OrderOut, PosOrderOut, PosStatusUpdateInput
from ....application.use_cases.orders.order_use_cases import UpdateOrderStatusUseCase
from ....auth import require_pos
from ....config import settings
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


logger = logging.getLogger(__name__)
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


# Endpoint temporal de mantenimiento para Render Free: ejecutar migraciones sin Shell.
@router.post("/bootstrap-db")
async def bootstrap_database(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    try:
        await _run_alembic_upgrade()
    except Exception:
        logger.warning("Database migration bootstrap failed.")
        raise HTTPException(status_code=500, detail="Database migration failed.")
    return {"ok": True, "message": "Database migrated successfully"}


@router.post("/pos/catalog-sync")
async def sync_pos_catalog(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    logger.info("POS catalog sync started.")
    try:
        result = await PosCatalogSyncService(db).sync()
    except PosClientError as exc:
        safe_message = _safe_log_message(exc.message)
        logger.warning(
            "Manual POS catalog sync failed with POS client error status_code=%s provider_status_code=%s message=%s",
            exc.status_code,
            exc.provider_status_code,
            safe_message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": safe_message},
        )
    except Exception as exc:
        logger.exception(
            "Manual POS catalog sync failed exception_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="POS catalog sync failed.")
    summary = result.to_dict()
    _log_catalog_sync_success(summary)
    return {"ok": True, **summary}


@router.get("/pos/catalog-audit")
async def audit_pos_catalog(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    logger.info("POS catalog audit requested.")
    return await PosCatalogAuditService(db).audit()


@router.get("/pos/catalog-audit/details")
async def audit_pos_catalog_details(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    logger.info("POS catalog audit details requested.")
    return await PosCatalogAuditService(db).details()


def _ensure_bootstrap_allowed(x_internal_token: str | None) -> None:
    if settings.is_production and not settings.debug:
        raise HTTPException(status_code=403, detail="Bootstrap deshabilitado en produccion.")
    if not settings.internal_bootstrap_token:
        raise HTTPException(status_code=503, detail="INTERNAL_BOOTSTRAP_TOKEN no configurado.")
    if not x_internal_token or x_internal_token != settings.internal_bootstrap_token:
        raise HTTPException(status_code=401, detail="Token interno invalido.")


def _ensure_migration_bootstrap_allowed(x_internal_token: str | None) -> None:
    if not settings.internal_bootstrap_token:
        raise HTTPException(status_code=503, detail="INTERNAL_BOOTSTRAP_TOKEN no configurado.")
    if not x_internal_token or not secrets.compare_digest(x_internal_token, settings.internal_bootstrap_token):
        raise HTTPException(status_code=403, detail="Forbidden")


def _log_catalog_sync_success(summary: dict) -> None:
    products = summary.get("products", {})
    promotions = summary.get("promotions", {})
    branches = summary.get("branches", {})
    logger.info(
        "POS catalog sync finished products_received=%s products_created=%s products_updated=%s "
        "products_deactivated=%s promotions_received=%s promotions_created=%s promotions_updated=%s "
        "branches_received=%s categories_created=%s categories_updated=%s skipped=%s errors=%s",
        products.get("received", 0),
        products.get("created", 0),
        products.get("updated", 0),
        products.get("deactivated", 0),
        promotions.get("received", 0),
        promotions.get("created", 0),
        promotions.get("updated", 0),
        branches.get("received", 0),
        summary.get("categories_created", 0),
        summary.get("categories_updated", 0),
        summary.get("skipped", 0),
        len(summary.get("errors", [])),
    )


def _safe_log_message(message: str) -> str:
    safe = message
    for secret in (settings.internal_bootstrap_token, settings.pos_internal_token):
        if secret:
            safe = safe.replace(secret, "***")
    return safe


async def _run_alembic_upgrade() -> None:
    await asyncio.to_thread(_upgrade_head_sync)


def _upgrade_head_sync() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    alembic_ini = repo_root / "alembic.ini"
    config = AlembicConfig(str(alembic_ini))
    database_url, _ = build_async_engine_config(
        settings.database_url,
        ca_cert=settings.aiven_ca_cert,
        ssl_insecure=settings.aiven_ssl_insecure,
        is_production=settings.is_production,
    )
    config.set_main_option("sqlalchemy.url", database_url.render_as_string(hide_password=False))
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
