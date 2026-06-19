from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.application.catalog.image_sync import (
    IMAGE_KEYS,
    ImageProduct,
    build_ecommerce_to_pos_image_candidates,
    clean,
    normalize_image_url,
    pos_product_from_payload,
)
from app.infrastructure.clients import PosClient, PosClientError
from app.infrastructure.database.connection import build_async_engine_config
from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM
from app.infrastructure.database.pos_catalog_sync import _extract_items
from app.infrastructure.database.session import AsyncSessionLocal


EXPORT_PATH = ROOT / "exports" / "image_sync_diff.csv"
ECOMMERCE_TO_POS_EXPORT_PATH = ROOT / "exports" / "ecommerce_to_pos_image_assignments.csv"
POS_DATABASE_URL_ENV = "POS_DATABASE_URL"
POS_TABLE_CANDIDATES = ("products", "productos")
POS_COLUMN_ALIASES = {
    "pos_product_id": ("id", "product_id", "pos_product_id", "external_id"),
    "sku": ("sku", "SKU", "code", "codigo", "external_code"),
    "name": ("name", "nombre", "title", "titulo"),
    "category": ("category", "categoria", "category_name", "categoria_nombre"),
    "subcategory": ("subcategory", "sub_category", "subcategoria", "subcategory_name"),
    "image_url": IMAGE_KEYS,
}
CSV_COLUMNS = (
    "sku",
    "product_name",
    "category",
    "subcategory",
    "pos_image_url",
    "ecommerce_image_url",
    "status",
)
ECOMMERCE_TO_POS_COLUMNS = (
    "sku",
    "pos_product_id",
    "name",
    "category",
    "subcategory",
    "ecommerce_image_url",
    "pos_current_image_url",
    "action",
)


async def load_ecommerce_products() -> dict[str, ImageProduct]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                select
                    p.sku,
                    p.name as product_name,
                    c.slug as category,
                    p.subcategory,
                    p.image_url
                from products p
                left join categories c on c.id = p.category_id
                where p.sku is not null and p.sku <> ''
                order by p.sku
                """
            )
        )
        rows = result.fetchall()

    return {
        clean(row._mapping["sku"]): ImageProduct(
            sku=clean(row._mapping["sku"]),
            product_name=clean(row._mapping["product_name"]),
            category=clean(row._mapping["category"]),
            subcategory=clean(row._mapping["subcategory"]),
            image_url=clean(row._mapping["image_url"]),
        )
        for row in rows
    }


async def load_pos_products() -> dict[str, ImageProduct]:
    pos_database_url = clean(os.getenv(POS_DATABASE_URL_ENV))
    if pos_database_url:
        return await load_pos_products_from_database(pos_database_url)
    return await load_pos_products_from_api()


async def load_pos_products_from_api() -> dict[str, ImageProduct]:
    payload = await PosClient().get_products()
    return {
        product.sku: product
        for product in (pos_product_from_payload(raw) for raw in _extract_items(payload, "products"))
        if product.sku
    }


async def load_pos_products_from_database(pos_database_url: str) -> dict[str, ImageProduct]:
    engine_url, engine_options = build_pos_engine_config(pos_database_url)
    engine = create_async_engine(engine_url, **engine_options)
    try:
        async with engine.connect() as connection:
            table_name, columns = await detect_pos_products_table(connection)
            query = build_pos_products_query(table_name, columns)
            result = await connection.execute(text(query))
            return {
                clean(row._mapping["sku"]): ImageProduct(
                    sku=clean(row._mapping["sku"]),
                    product_name=clean(row._mapping["product_name"]),
                    category=clean(row._mapping["category"]),
                    subcategory=clean(row._mapping["subcategory"]),
                    image_url=clean(row._mapping["image_url"]),
                    pos_product_id=clean(row._mapping["pos_product_id"]),
                )
                for row in result.fetchall()
                if clean(row._mapping["sku"])
            }
    finally:
        await engine.dispose()


def build_pos_engine_config(pos_database_url: str):
    url = make_url(pos_database_url)
    if url.drivername == "mysql":
        url = url.set(drivername="mysql+aiomysql")
    engine_url, engine_options = build_async_engine_config(
        url.render_as_string(hide_password=False),
        ca_cert=settings.aiven_ca_cert,
        ssl_insecure=settings.aiven_ssl_insecure,
        is_production=settings.is_production,
        echo=settings.debug,
        pool_pre_ping=False,
    )
    return engine_url, engine_options


async def detect_pos_products_table(connection) -> tuple[str, set[str]]:
    database_name = await connection.scalar(text("select database()"))
    for table_name in POS_TABLE_CANDIDATES:
        result = await connection.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = :database_name and table_name = :table_name
                """
            ),
            {"database_name": database_name, "table_name": table_name},
        )
        columns = {clean(row[0]) for row in result.fetchall()}
        if columns and any(column in columns for column in POS_COLUMN_ALIASES["sku"]):
            return table_name, columns
    raise RuntimeError("Could not find a POS products table with a SKU column. Tried: products, productos.")


def build_pos_products_query(table_name: str, columns: set[str]) -> str:
    return f"""
        select
            {column_expr(columns, POS_COLUMN_ALIASES["sku"])} as sku,
            {column_expr(columns, POS_COLUMN_ALIASES["pos_product_id"])} as pos_product_id,
            {column_expr(columns, POS_COLUMN_ALIASES["name"])} as product_name,
            {column_expr(columns, POS_COLUMN_ALIASES["category"])} as category,
            {column_expr(columns, POS_COLUMN_ALIASES["subcategory"])} as subcategory,
            {column_expr(columns, POS_COLUMN_ALIASES["image_url"])} as image_url
        from {table_name}
    """


def column_expr(columns: set[str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        if alias in columns:
            return f"`{alias}`"
    return "''"


def compare_products(
    ecommerce_products: dict[str, ImageProduct],
    pos_products: dict[str, ImageProduct],
) -> list[dict[str, str]]:
    rows = []
    for sku in sorted(set(ecommerce_products) | set(pos_products)):
        ecommerce = ecommerce_products.get(sku)
        pos = pos_products.get(sku)
        rows.append(compare_sku(sku, ecommerce, pos))
    return rows


def compare_sku(
    sku: str,
    ecommerce: ImageProduct | None,
    pos: ImageProduct | None,
) -> dict[str, str]:
    if ecommerce is None:
        status = "sku_not_found_in_ecommerce"
    elif pos is None:
        status = "sku_not_found_in_pos"
    else:
        pos_image = normalize_image_url(pos.image_url)
        ecommerce_image = normalize_image_url(ecommerce.image_url)
        if not pos_image and not ecommerce_image:
            status = "missing_in_both"
        elif not pos_image:
            status = "missing_in_pos"
        elif not ecommerce_image:
            status = "missing_in_ecommerce"
        elif pos_image == ecommerce_image:
            status = "same_image"
        else:
            status = "different_image"

    source = ecommerce or pos
    return {
        "sku": sku,
        "product_name": source.product_name if source else "",
        "category": source.category if source else "",
        "subcategory": source.subcategory if source else "",
        "pos_image_url": pos.image_url if pos else "",
        "ecommerce_image_url": ecommerce.image_url if ecommerce else "",
        "status": status,
    }


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def main() -> int:
    ecommerce_products = await load_ecommerce_products()
    pos_products = await load_pos_products()
    rows = compare_products(ecommerce_products, pos_products)
    ecommerce_to_pos_assignments = build_ecommerce_to_pos_image_candidates(ecommerce_products, pos_products)
    write_csv(EXPORT_PATH, CSV_COLUMNS, rows)
    write_csv(ECOMMERCE_TO_POS_EXPORT_PATH, ECOMMERCE_TO_POS_COLUMNS, ecommerce_to_pos_assignments)
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    print("POS/ecommerce image comparison finished.")
    print(f"- total ecommerce products: {len(ecommerce_products)}")
    print(f"- total pos products: {len(pos_products)}")
    print(f"- rows exported: {len(rows)}")
    for status in (
        "same_image",
        "missing_in_pos",
        "missing_in_ecommerce",
        "missing_in_both",
        "different_image",
    ):
        print(f"- {status}: {status_counts.get(status, 0)}")
    print(f"- ecommerce_to_pos_assignments_count: {len(ecommerce_to_pos_assignments)}")
    print(f"- output: {EXPORT_PATH.relative_to(ROOT)}")
    print(f"- assignments output: {ECOMMERCE_TO_POS_EXPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except PosClientError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        raise SystemExit(1)
    except SQLAlchemyError as exc:
        print(f"Error: Could not read database for image comparison: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
