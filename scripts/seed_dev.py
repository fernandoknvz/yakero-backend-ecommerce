import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.database.dev_seed import (
    DEMO_USER_EMAIL,
    DEMO_USER_PASSWORD,
    seed_dev_data,
)
from app.infrastructure.database.session import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as session:
        summary = await seed_dev_data(session)
        await session.commit()

    print("Seed local/dev completado")
    print(f"- categorias activas: {summary.active_categories}")
    print(f"- productos totales: {summary.total_products}")
    print(f"- productos activos: {summary.active_products}")
    print(f"- usuario demo: {summary.demo_user_email}")
    print(f"- password demo: {DEMO_USER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
