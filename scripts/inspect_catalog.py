import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.infrastructure.database.session import AsyncSessionLocal


QUERIES = {
    "categories_active": "select count(*) from categories where is_active = 1",
    "products_total": "select count(*) from products",
    "products_active": "select count(*) from products where is_available = 1",
    "products_with_valid_category": """
        select count(*)
        from products p
        join categories c on c.id = p.category_id
    """,
    "products_with_invalid_category": """
        select count(*)
        from products p
        left join categories c on c.id = p.category_id
        where c.id is null
    """,
    "products_without_price": """
        select count(*)
        from products
        where price is null or price <= 0
    """,
}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print("Diagnostico de catalogo")
        for name, query in QUERIES.items():
            value = await session.scalar(text(query))
            print(f"- {name}: {value}")

        print("\nCategorias activas")
        result = await session.execute(
            text(
                """
                select c.id, c.name, c.slug, c.sort_order, count(p.id) as product_count
                from categories c
                left join products p on p.category_id = c.id and p.is_available = 1
                where c.is_active = 1
                group by c.id, c.name, c.slug, c.sort_order
                order by c.sort_order, c.id
                """
            )
        )
        for row in result.fetchall():
            print(dict(row._mapping))

        print("\nProductos")
        result = await session.execute(
            text(
                """
                select
                    p.id,
                    p.name,
                    p.slug,
                    p.category_id,
                    c.slug as category_slug,
                    p.price,
                    p.is_available,
                    p.image_url
                from products p
                left join categories c on c.id = p.category_id
                order by p.id
                """
            )
        )
        for row in result.fetchall():
            print(dict(row._mapping))


if __name__ == "__main__":
    asyncio.run(main())
