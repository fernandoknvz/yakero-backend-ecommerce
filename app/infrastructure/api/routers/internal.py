import asyncio
from collections import Counter
import logging
import secrets
from pathlib import Path
from decimal import Decimal
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.dev_seed import DEMO_COUPON_CODE, DEMO_USER_EMAIL, seed_dev_data
from ...database.connection import build_async_engine_config
from ...database.models.orm_models import CategoryORM, CouponORM, ProductORM, UserORM
from ...database.pos_catalog_audit import PosCatalogAuditService
from ...database.pos_catalog_sync import PosCatalogSyncService
from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import AsyncSessionLocal, get_db
from ...clients import PosClient, PosClientError
from ..errors import domain_error_to_http
from ....application.dtos.schemas import OrderOut, PosOrderOut, PosStatusUpdateInput
from ....application.use_cases.orders.order_use_cases import UpdateOrderStatusUseCase
from ....auth import require_pos
from ....config import settings
from ....domain.exceptions import DomainError
from ....domain.models.entities import User
from ....application.catalog.image_sync import (
    ImageProduct,
    build_ecommerce_to_pos_image_candidates,
    pos_product_from_payload,
)
from ....application.catalog.image_assignments import (
    apply_product_image_assignments,
    load_assignments,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["POS Interno"])
DEFAULT_IMAGE_ASSIGNMENTS_CSV = Path("exports/empanadas_product_image_assignments.csv")


class CatalogImageAssignmentsImportInput(BaseModel):
    csv_path: str | None = None
    dry_run: bool = True
    fail_on_missing: bool = True


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


@router.post("/catalog/image-assignments/import")
async def import_catalog_image_assignments(
    data: CatalogImageAssignmentsImportInput | None = None,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    payload = data or CatalogImageAssignmentsImportInput()
    csv_path = _resolve_versioned_csv_path(payload.csv_path)

    try:
        assignments = load_assignments(csv_path)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="CSV file not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        result = await apply_product_image_assignments(
            db,
            assignments,
            dry_run=payload.dry_run,
            fail_on_missing=payload.fail_on_missing,
        )
    except Exception:
        logger.exception("Catalog image assignment import failed.")
        raise HTTPException(status_code=500, detail="Image assignment import failed.")

    return {
        "dry_run": payload.dry_run,
        "total_rows": result.received,
        "updated": result.updated,
        "skipped": result.skipped,
        "missing": result.missing,
        "errors": result.errors,
    }


@router.get("/catalog/image-audit/db-only")
async def catalog_image_audit_db_only(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    logger.info("Catalog DB-only image audit requested.")
    return await _build_catalog_image_audit_db_only(db)


@router.get("/catalog/image-sync/ecommerce-to-pos-candidates")
async def catalog_ecommerce_to_pos_image_candidates(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    _ensure_migration_bootstrap_allowed(x_internal_token)
    logger.info("Catalog ecommerce-to-POS image candidates requested.")
    return await _build_ecommerce_to_pos_image_candidates(db)


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


def _resolve_versioned_csv_path(csv_path: str | None) -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    requested_path = (csv_path or "").strip() or str(DEFAULT_IMAGE_ASSIGNMENTS_CSV)
    relative_path = Path(requested_path)
    if relative_path.is_absolute():
        raise HTTPException(status_code=400, detail="CSV path must be relative.")

    resolved = (repo_root / relative_path).resolve()
    exports_root = (repo_root / "exports").resolve()
    try:
        resolved.relative_to(exports_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="CSV path must be inside exports/.")

    if resolved.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="CSV path must end with .csv.")
    return resolved


async def _build_catalog_image_audit_db_only(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(ProductORM, CategoryORM)
        .join(CategoryORM, ProductORM.category_id == CategoryORM.id)
        .where(ProductORM.is_available.is_(True), CategoryORM.is_active.is_(True))
        .order_by(CategoryORM.slug, ProductORM.subcategory, ProductORM.name)
    )
    rows = result.all()
    products = [(product, category) for product, category in rows]
    without_image = [
        (product, category)
        for product, category in products
        if not _has_catalog_image(product.image_url)
    ]
    with_image_count = len(products) - len(without_image)
    coverage_percentage = round((with_image_count / len(products)) * 100, 2) if products else 0

    by_category = Counter(_category_label(category) for _, category in without_image)
    by_subcategory = Counter(_subcategory_label(product) for product, _ in without_image)

    return {
        "total_products": len(products),
        "products_with_image": with_image_count,
        "products_without_image_count": len(without_image),
        "coverage_percentage": coverage_percentage,
        "without_image_by_category": [
            {"category": category, "products_without_image": count}
            for category, count in sorted(by_category.items())
        ],
        "without_image_by_subcategory": [
            {"subcategory": subcategory, "products_without_image": count}
            for subcategory, count in sorted(by_subcategory.items())
        ],
        "products_without_image": [
            {
                "sku": product.sku,
                "name": product.name,
                "category": _category_label(category),
                "subcategory": product.subcategory,
                "price": _format_money(product.price),
                "active": bool(product.is_available and category.is_active),
                "available_for_ecommerce": bool(product.is_available and category.is_active),
            }
            for product, category in without_image
        ],
    }


def _has_catalog_image(value: object) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def _category_label(category: CategoryORM) -> str:
    return category.slug or category.name or ""


def _subcategory_label(product: ProductORM) -> str:
    return product.subcategory or "sin_subcategoria"


def _format_money(value: object) -> str:
    if value is None:
        return ""
    decimal = Decimal(str(value))
    if decimal == decimal.to_integral_value():
        return str(decimal.quantize(Decimal("1")))
    return str(decimal)


async def _build_ecommerce_to_pos_image_candidates(db: AsyncSession) -> dict[str, Any]:
    ecommerce_products = await _load_ecommerce_image_products(db)
    pos_products = await _fetch_pos_image_products()
    candidates = build_ecommerce_to_pos_image_candidates(ecommerce_products, pos_products)
    return {
        "total_ecommerce_products": len(ecommerce_products),
        "total_pos_products": len(pos_products),
        "candidates_count": len(candidates),
        "candidates": candidates,
    }


async def _fetch_pos_image_products() -> dict[str, ImageProduct]:
    try:
        pos_payload = await PosClient().get_products()
    except PosClientError as exc:
        logger.exception("Could not fetch POS catalog for ecommerce-to-POS image candidates.")
        detail = {"message": "Could not fetch POS catalog"}
        if exc.status_code:
            detail["status_code"] = exc.status_code
        raise HTTPException(status_code=502, detail=detail)

    pos_items = _extract_pos_items_or_raise(pos_payload, "products")
    return {
        product.sku: product
        for product in (pos_product_from_payload(raw) for raw in pos_items)
        if product.sku
    }


async def _load_ecommerce_image_products(db: AsyncSession) -> dict[str, ImageProduct]:
    result = await db.execute(
        select(ProductORM, CategoryORM)
        .join(CategoryORM, ProductORM.category_id == CategoryORM.id)
        .where(ProductORM.sku.is_not(None), ProductORM.sku != "")
        .order_by(ProductORM.sku)
    )
    return {
        str(product.sku).strip(): ImageProduct(
            sku=str(product.sku).strip(),
            product_name=product.name or "",
            category=category.slug or category.name or "",
            subcategory=product.subcategory or "",
            image_url=product.image_url or "",
        )
        for product, category in result.all()
        if product.sku and str(product.sku).strip()
    }


def _extract_pos_items_or_raise(payload: Any, preferred_key: str) -> list[dict[str, Any]]:
    if payload in (None, ""):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Invalid POS catalog response format")

    for key in (preferred_key, "results", "items", "data"):
        if key not in payload:
            continue
        value = payload.get(key)
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        raise HTTPException(status_code=502, detail="Invalid POS catalog response format")

    catalog = payload.get("catalog")
    if isinstance(catalog, dict):
        value = catalog.get(preferred_key)
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        raise HTTPException(status_code=502, detail="Invalid POS catalog response format")

    if not payload:
        return []
    raise HTTPException(status_code=502, detail="Invalid POS catalog response format")


def _extract_pos_items(payload: Any, preferred_key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (preferred_key, "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    catalog = payload.get("catalog")
    if isinstance(catalog, dict):
        value = catalog.get(preferred_key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


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
