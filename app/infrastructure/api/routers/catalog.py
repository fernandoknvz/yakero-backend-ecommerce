from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...database.models.orm_models import CategoryORM, ModifierGroupORM, ProductORM
from ...database.repositories.sql_repositories import (
    SQLCategoryRepository,
    SQLProductRepository,
    SQLPromotionRepository,
    _map_product,
)
from ...database.session import get_db
from ....application.dtos.schemas import (
    CategoryOut,
    CategorySummaryOut,
    ProductCategoryRefOut,
    ProductDetailOut,
    ProductFlagsOut,
    ProductListItemOut,
    PromotionOut,
    PromotionSummaryOut,
)


products_router = APIRouter(prefix="/products", tags=["Productos"])
categories_router = APIRouter(prefix="/categories", tags=["Categorias"])
promotions_router = APIRouter(prefix="/promotions", tags=["Promociones"])


def _build_product_flags(product) -> ProductFlagsOut:
    return ProductFlagsOut(
        is_configurable=bool(product.modifier_groups),
        has_required_modifiers=any(group.is_required for group in product.modifier_groups),
        has_optional_modifiers=any(not group.is_required for group in product.modifier_groups),
        has_image=bool(product.image_url),
    )


def _build_category_ref(category) -> ProductCategoryRefOut:
    return ProductCategoryRefOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        ticket_tag=category.ticket_tag,
        image_url=category.image_url,
        sort_order=category.sort_order,
    )


def _to_product_list_item(product, category) -> ProductListItemOut:
    return ProductListItemOut(
        id=product.id,
        category_id=product.category_id,
        sku=product.sku,
        name=product.name,
        slug=product.slug,
        description=product.description,
        price=product.price,
        image_url=product.image_url,
        ticket_tag=product.ticket_tag,
        is_available=product.is_available,
        category=_build_category_ref(category),
        flags=_build_product_flags(product),
    )


def _sort_products(products: list, sort: str) -> list:
    sort_key = sort.lower()
    sorters = {
        "default": lambda item: (item.sort_order, item.name.lower()),
        "name_asc": lambda item: item.name.lower(),
        "name_desc": lambda item: item.name.lower(),
        "price_asc": lambda item: (item.price, item.name.lower()),
        "price_desc": lambda item: (item.price, item.name.lower()),
    }
    if sort_key not in sorters:
        raise HTTPException(status_code=422, detail="Parametro sort invalido")
    reverse = sort_key in {"name_desc", "price_desc"}
    return sorted(products, key=sorters[sort_key], reverse=reverse)


@categories_router.get("/", response_model=list[CategorySummaryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await SQLCategoryRepository(db).get_all_active()


@products_router.get("/", response_model=list[ProductListItemOut])
async def list_products(
    category_id: Optional[int] = Query(default=None, ge=1),
    category_slug: Optional[str] = Query(default=None, min_length=2, max_length=120),
    q: Optional[str] = Query(default=None, min_length=2, max_length=80),
    sort: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    category_repo = SQLCategoryRepository(db)
    categories = await category_repo.get_all_active()
    categories_by_id = {category.id: category for category in categories}
    categories_by_slug = {category.slug: category for category in categories}

    resolved_category_id = category_id
    if category_slug:
        category = categories_by_slug.get(category_slug)
        if not category:
            raise HTTPException(status_code=404, detail="Categoria no encontrada")
        resolved_category_id = category.id

    repo = SQLProductRepository(db)
    if q:
        products = await repo.search(q)
    elif resolved_category_id:
        products = await repo.get_by_category(resolved_category_id)
    else:
        products = await repo.get_all_active()

    products = [product for product in products if product.category_id in categories_by_id]
    products = _sort_products(products, sort)
    return [
        _to_product_list_item(product, categories_by_id[product.category_id])
        for product in products
    ]


@products_router.get("/{product_id}", response_model=ProductDetailOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product_repo = SQLProductRepository(db)
    product = await product_repo.get_by_id(product_id)
    if not product or not product.is_available:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    category = await SQLCategoryRepository(db).get_by_id(product.category_id)
    if not category or not category.is_active:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    promotions = await SQLPromotionRepository(db).get_all_active()
    return ProductDetailOut(
        id=product.id,
        category_id=product.category_id,
        sku=product.sku,
        name=product.name,
        slug=product.slug,
        description=product.description,
        price=product.price,
        image_url=product.image_url,
        ticket_tag=product.ticket_tag,
        is_available=product.is_available,
        category=_build_category_ref(category),
        flags=_build_product_flags(product),
        modifier_groups=product.modifier_groups,
        applicable_promotions=[
            PromotionSummaryOut(
                id=promotion.id,
                name=promotion.name,
                description=promotion.description,
                promotion_type=promotion.promotion_type,
                value=promotion.value,
                image_url=promotion.image_url,
            )
            for promotion in promotions
        ],
    )


@categories_router.get("/menu", response_model=list[CategoryOut])
async def full_menu(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CategoryORM)
        .where(CategoryORM.is_active == True)
        .options(
            selectinload(CategoryORM.products)
            .selectinload(ProductORM.modifier_groups)
            .selectinload(ModifierGroupORM.options)
        )
        .order_by(CategoryORM.sort_order)
    )
    categories = result.scalars().all()

    return [
        CategoryOut(
            id=category.id,
            name=category.name,
            slug=category.slug,
            ticket_tag=category.ticket_tag,
            image_url=category.image_url,
            sort_order=category.sort_order,
            products=[_map_product(product) for product in category.products if product.is_available],
        )
        for category in categories
    ]


@promotions_router.get("/", response_model=list[PromotionOut])
async def list_promotions(db: AsyncSession = Depends(get_db)):
    return await SQLPromotionRepository(db).get_all_active()
