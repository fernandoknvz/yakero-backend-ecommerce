from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...database.models.orm_models import CategoryORM, ModifierGroupORM, ProductORM
from ...database.repositories.sql_repositories import (
    SQLProductRepository,
    SQLPromotionRepository,
    _map_product,
)
from ...database.session import get_db
from ....application.dtos.schemas import CategoryOut, ProductOut, PromotionOut


products_router = APIRouter(prefix="/products", tags=["Productos"])
categories_router = APIRouter(prefix="/categories", tags=["Categorias"])
promotions_router = APIRouter(prefix="/promotions", tags=["Promociones"])


@products_router.get("/", response_model=list[ProductOut])
async def list_products(
    category_id: Optional[int] = Query(default=None, ge=1),
    q: Optional[str] = Query(default=None, min_length=2, max_length=80),
    db: AsyncSession = Depends(get_db),
):
    repo = SQLProductRepository(db)
    if q:
        return await repo.search(q)
    if category_id:
        return await repo.get_by_category(category_id)
    return await repo.get_all_active()


@products_router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await SQLProductRepository(db).get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


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
