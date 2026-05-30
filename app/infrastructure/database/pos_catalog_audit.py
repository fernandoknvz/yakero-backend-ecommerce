from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models.orm_models import CategoryORM, ProductORM, PromotionORM


class PosCatalogAuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def audit(self) -> dict[str, Any]:
        categories = await self._load_all(CategoryORM)
        products = await self._load_all(ProductORM)
        promotions = await self._load_all(PromotionORM)
        category_ids = {category.id for category in categories if category.id is not None}

        return {
            "ok": True,
            "products": self._audit_products(products, category_ids),
            "promotions": self._audit_promotions(promotions),
            "categories": {
                "total": len(categories),
                "names": sorted(category.name for category in categories if category.name),
            },
            "branches": {
                "total": 0,
                "active": 0,
            },
        }

    async def details(self) -> dict[str, Any]:
        categories = await self._load_all(CategoryORM)
        products = await self._load_all(ProductORM)
        promotions = await self._load_all(PromotionORM)
        categories_by_id = {category.id: category for category in categories if category.id is not None}

        return {
            "products_without_price": [
                self._product_detail(product, categories_by_id)
                for product in products
                if _is_missing_money(product.price)
            ],
            "products_without_image": [
                self._product_detail(product, categories_by_id)
                for product in products
                if not _clean(product.image_url)
            ][:20],
            "promotions_without_image": [
                self._promotion_detail(promotion)
                for promotion in promotions
                if not _clean(promotion.image_url)
            ],
        }

    async def _load_all(self, model):
        result = await self._session.execute(select(model))
        return result.scalars().all()

    def _audit_products(self, products: list[ProductORM], category_ids: set[int]) -> dict[str, Any]:
        skus = [_clean(product.sku) for product in products if _clean(product.sku)]
        return {
            "total": len(products),
            "active": sum(1 for product in products if bool(product.is_available)),
            "available_for_ecommerce": sum(1 for product in products if bool(product.is_available)),
            "without_price": sum(1 for product in products if _is_missing_money(product.price)),
            "without_category": sum(
                1
                for product in products
                if product.category_id is None or product.category_id not in category_ids
            ),
            "without_sku": sum(1 for product in products if not _clean(product.sku)),
            "without_image": sum(1 for product in products if not _clean(product.image_url)),
            "duplicate_skus": _duplicates(skus),
            "duplicate_pos_product_ids": [],
        }

    def _audit_promotions(self, promotions: list[PromotionORM]) -> dict[str, Any]:
        codes = [_clean(promotion.external_code) for promotion in promotions if _clean(promotion.external_code)]
        return {
            "total": len(promotions),
            "active": sum(1 for promotion in promotions if bool(promotion.is_active)),
            "without_price": sum(1 for promotion in promotions if _is_missing_money(promotion.value)),
            "without_code": sum(1 for promotion in promotions if not _clean(promotion.external_code)),
            "without_image": sum(1 for promotion in promotions if not _clean(promotion.image_url)),
            "duplicate_codes": _duplicates(codes),
        }

    def _product_detail(
        self,
        product: ProductORM,
        categories_by_id: dict[int, CategoryORM],
    ) -> dict[str, Any]:
        category = categories_by_id.get(product.category_id)
        return {
            "sku": product.sku,
            "name": product.name,
            "category": category.name if category else None,
            "subcategory": getattr(product, "subcategory", None),
            "price": product.price,
            "is_available": bool(product.is_available),
        }

    def _promotion_detail(self, promotion: PromotionORM) -> dict[str, Any]:
        return {
            "code": promotion.external_code,
            "name": promotion.name,
            "price": promotion.value,
            "is_active": bool(promotion.is_active),
        }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_missing_money(value: Any) -> bool:
    if value is None:
        return True
    try:
        return Decimal(str(value)) <= 0
    except Exception:
        return True


def _duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)
