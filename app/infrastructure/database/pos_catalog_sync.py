from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.models.enums import TicketTag
from ..clients import PosClient
from .models.orm_models import CategoryORM, ProductORM, PromotionORM


logger = logging.getLogger(__name__)


@dataclass
class PosCatalogEntitySyncResult:
    received: int = 0
    created: int = 0
    updated: int = 0
    deactivated: int = 0


@dataclass
class PosCatalogSyncResult:
    source: str = "pos"
    products: PosCatalogEntitySyncResult = field(default_factory=PosCatalogEntitySyncResult)
    promotions: PosCatalogEntitySyncResult = field(default_factory=PosCatalogEntitySyncResult)
    branches: PosCatalogEntitySyncResult = field(default_factory=PosCatalogEntitySyncResult)
    categories_created: int = 0
    categories_updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PosCatalogSyncService:
    def __init__(self, session: AsyncSession, client: PosClient | None = None):
        self._session = session
        self._client = client or PosClient()

    async def sync(self) -> PosCatalogSyncResult:
        result = PosCatalogSyncResult()
        logger.info("POS catalog sync started.")

        products_payload = await self._client.get_products()
        promotions_payload = await self._client.get_promotions()
        branches_payload = await self._client.get_branches()
        products = _extract_items(products_payload, "products")
        promotions = _extract_items(promotions_payload, "promotions")
        branches = _extract_items(branches_payload, "branches")
        result.products.received = len(products)
        result.promotions.received = len(promotions)
        result.branches.received = len(branches)

        logger.info(
            "POS catalog sync payload received products=%s promotions=%s branches=%s",
            result.products.received,
            result.promotions.received,
            result.branches.received,
        )

        categories_by_slug = await self._load_categories_by_slug()
        products_by_sku = await self._load_products_by_sku()
        promotions_by_external_code = await self._load_promotions_by_external_code()
        received_product_skus: set[str] = set()

        for index, raw_product in enumerate(products, start=1):
            try:
                synced = await self._sync_product(
                    raw_product,
                    categories_by_slug,
                    products_by_sku,
                    result,
                    received_product_skus,
                    index,
                )
                if not synced:
                    result.skipped += 1
            except Exception as exc:
                result.skipped += 1
                message = f"product[{index}] mapping failed: {type(exc).__name__}"
                result.errors.append(message)
                logger.warning("%s", message)

        self._deactivate_missing_products(products_by_sku, received_product_skus, result)

        for index, raw_promotion in enumerate(promotions, start=1):
            try:
                synced = await self._sync_promotion(
                    raw_promotion,
                    promotions_by_external_code,
                    result,
                    index,
                )
                if not synced:
                    result.skipped += 1
            except Exception as exc:
                result.skipped += 1
                message = f"promotion[{index}] mapping failed: {type(exc).__name__}"
                result.errors.append(message)
                logger.warning("%s", message)

        await self._session.flush()
        logger.info(
            "POS catalog sync finished products_received=%s products_created=%s "
            "products_updated=%s products_deactivated=%s promotions_received=%s "
            "promotions_created=%s promotions_updated=%s branches_received=%s "
            "categories_created=%s categories_updated=%s skipped=%s errors=%s",
            result.products.received,
            result.products.created,
            result.products.updated,
            result.products.deactivated,
            result.promotions.received,
            result.promotions.created,
            result.promotions.updated,
            result.branches.received,
            result.categories_created,
            result.categories_updated,
            result.skipped,
            len(result.errors),
        )
        return result

    async def _sync_product(
        self,
        raw: dict[str, Any],
        categories_by_slug: dict[str, CategoryORM],
        products_by_sku: dict[str, ProductORM],
        result: PosCatalogSyncResult,
        received_product_skus: set[str],
        index: int,
    ) -> bool:
        sku = _string_value(raw, "sku", "SKU", "code", "external_code")
        if not sku:
            result.errors.append(f"product[{index}] skipped: missing sku")
            return False
        received_product_skus.add(sku)

        category_data = _category_data(raw)
        category_slug = _category_slug(category_data, raw)
        category_name = _category_name(category_data, raw)
        if not category_slug or not category_name:
            result.errors.append(f"product[{index}] skipped: missing category")
            return False

        category = categories_by_slug.get(category_slug)
        category_values = {
            "name": category_name,
            "slug": category_slug,
            "ticket_tag": _ticket_tag(raw, category_data),
            "image_url": _string_value(category_data, "image_url", "image", "photo_url"),
            "sort_order": _int_value(category_data, "sort_order", "position", default=0),
            "is_active": _active_value(category_data),
        }
        if category is None:
            category = CategoryORM(**category_values)
            self._session.add(category)
            await self._session.flush()
            categories_by_slug[category_slug] = category
            result.categories_created += 1
        else:
            _assign(category, category_values)
            result.categories_updated += 1

        product_values = {
            "category_id": category.id,
            "sku": sku,
            "name": _required_string(raw, "name", "nombre", "title"),
            "slug": _slugify(f"{_required_string(raw, 'name', 'nombre', 'title')}-{sku}"),
            "description": _string_value(raw, "description", "descripcion", "detail"),
            "price": _decimal_value(raw, "price", "precio", "amount", "value"),
            "image_url": _string_value(raw, "image_url", "image", "photo_url", "picture"),
            "ticket_tag": _ticket_tag(raw, category_data),
            "is_available": _active_value(raw) and _available_for_ecommerce(raw),
            "sort_order": _int_value(raw, "sort_order", "position", "order", default=0),
        }

        product = products_by_sku.get(sku)
        if product is None:
            product = ProductORM(**product_values)
            self._session.add(product)
            products_by_sku[sku] = product
            result.products.created += 1
        else:
            was_available = bool(product.is_available)
            _assign(product, product_values)
            result.products.updated += 1
            if was_available and not product.is_available:
                result.products.deactivated += 1
        return True

    async def _sync_promotion(
        self,
        raw: dict[str, Any],
        promotions_by_external_code: dict[str, PromotionORM],
        result: PosCatalogSyncResult,
        index: int,
    ) -> bool:
        external_code = _string_value(raw, "promo_code", "external_code", "code", "sku")
        if not external_code:
            raw_id = _string_value(raw, "id", "external_id")
            name = _string_value(raw, "name", "nombre", "title")
            external_code = raw_id or (f"promo-{_slugify(name)}" if name else "")
        if not external_code:
            result.errors.append(f"promotion[{index}] skipped: missing external_code")
            return False

        promotion_values = {
            "external_code": external_code,
            "name": _required_string(raw, "name", "nombre", "title"),
            "description": _string_value(raw, "description", "descripcion", "detail"),
            "promotion_type": _string_value(raw, "promotion_type", "type", default="bundle") or "bundle",
            "value": _decimal_value(raw, "value", "price", "precio", "amount", "discount_value"),
            "image_url": _string_value(raw, "image_url", "image", "photo_url", "picture"),
            "is_active": _active_value(raw) and _available_for_ecommerce(raw),
            "starts_at": _datetime_value(raw, "starts_at", "start_at", "valid_from"),
            "ends_at": _datetime_value(raw, "ends_at", "end_at", "valid_until"),
        }

        promotion = promotions_by_external_code.get(external_code)
        if promotion is None:
            promotion = PromotionORM(**promotion_values)
            self._session.add(promotion)
            promotions_by_external_code[external_code] = promotion
            result.promotions.created += 1
        else:
            was_active = bool(promotion.is_active)
            _assign(promotion, promotion_values)
            result.promotions.updated += 1
            if was_active and not promotion.is_active:
                result.promotions.deactivated += 1
        return True

    def _deactivate_missing_products(
        self,
        products_by_sku: dict[str, ProductORM],
        received_product_skus: set[str],
        result: PosCatalogSyncResult,
    ) -> None:
        for sku, product in products_by_sku.items():
            if sku in received_product_skus or not product.is_available:
                continue
            product.is_available = False
            result.products.deactivated += 1

    async def _load_categories_by_slug(self) -> dict[str, CategoryORM]:
        result = await self._session.execute(select(CategoryORM))
        return {category.slug: category for category in result.scalars().all()}

    async def _load_products_by_sku(self) -> dict[str, ProductORM]:
        result = await self._session.execute(select(ProductORM).where(ProductORM.sku.is_not(None)))
        return {product.sku: product for product in result.scalars().all()}

    async def _load_promotions_by_external_code(self) -> dict[str, PromotionORM]:
        result = await self._session.execute(
            select(PromotionORM).where(PromotionORM.external_code.is_not(None))
        )
        return {promotion.external_code: promotion for promotion in result.scalars().all()}


def _extract_items(payload: dict[str, Any] | list[Any], preferred_key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    candidates = (
        preferred_key,
        "results",
        "items",
        "data",
    )
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    catalog = payload.get("catalog")
    if isinstance(catalog, dict):
        value = catalog.get(preferred_key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _category_data(raw: dict[str, Any]) -> dict[str, Any]:
    category = raw.get("category") or raw.get("categoria")
    return category if isinstance(category, dict) else {}


def _category_slug(category: dict[str, Any], raw: dict[str, Any]) -> str:
    return (
        _string_value(category, "slug", "code", "external_code")
        or _string_value(raw, "category_slug", "categoria_slug")
        or _slugify(_category_name(category, raw))
    )


def _category_name(category: dict[str, Any], raw: dict[str, Any]) -> str:
    return (
        _string_value(category, "name", "nombre", "title")
        or _string_value(raw, "category_name", "categoria_nombre", "category")
    )


def _ticket_tag(raw: dict[str, Any], category: dict[str, Any] | None = None) -> TicketTag:
    value = _string_value(raw, "ticket_tag", "kitchen_destination", "destination")
    if not value and category:
        value = _string_value(category, "ticket_tag", "kitchen_destination", "destination")
    normalized = _slugify(value).replace("-", "_")
    mapping = {
        "cocina_sushi": TicketTag.COCINA_SUSHI,
        "sushi": TicketTag.COCINA_SUSHI,
        "cocina_sandwich": TicketTag.COCINA_SANDWICH,
        "sandwich": TicketTag.COCINA_SANDWICH,
        "caja": TicketTag.CAJA,
        "ninguna": TicketTag.NONE,
        "none": TicketTag.NONE,
    }
    return mapping.get(normalized, TicketTag.CAJA)


def _active_value(raw: dict[str, Any]) -> bool:
    value = _first_value(raw, "active", "activo", "is_active", "enabled")
    if value is None:
        return True
    return _bool_value(value)


def _available_for_ecommerce(raw: dict[str, Any]) -> bool:
    value = _first_value(raw, "available_for_ecommerce", "is_available", "available", "disponible")
    if value is None:
        return True
    return _bool_value(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "activo", "active", "disponible"}
    return bool(value)


def _required_string(raw: dict[str, Any], *keys: str) -> str:
    value = _string_value(raw, *keys)
    if not value:
        raise ValueError(f"Missing required field: {'/'.join(keys)}")
    return value


def _string_value(raw: dict[str, Any], *keys: str, default: str = "") -> str:
    value = _first_value(raw, *keys)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            value = raw[key]
            if value is not None and value != "":
                return value
    return None


def _decimal_value(raw: dict[str, Any], *keys: str) -> Decimal:
    value = _first_value(raw, *keys)
    if value is None:
        return Decimal("0")
    if isinstance(value, str):
        value = _normalize_decimal_string(value)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _int_value(raw: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = _first_value(raw, *keys)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _datetime_value(raw: dict[str, Any], *keys: str) -> datetime | None:
    value = _first_value(raw, *keys)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _assign(target: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(target, key, value)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "sin-nombre"


def _normalize_decimal_string(value: str) -> str:
    normalized = re.sub(r"[^\d,.-]", "", value.strip())
    if "," in normalized and "." in normalized:
        return normalized.replace(".", "").replace(",", ".")
    if "," in normalized:
        return normalized.replace(",", ".")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", normalized):
        return normalized.replace(".", "")
    return normalized
