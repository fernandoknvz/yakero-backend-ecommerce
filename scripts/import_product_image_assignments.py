from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM
from app.infrastructure.database.session import AsyncSessionLocal


REQUIRED_COLUMNS = {"sku", "image_url"}


@dataclass(frozen=True)
class ProductImageAssignment:
    sku: str
    image_url: str
    category: str = ""
    subcategory: str = ""
    name: str = ""


@dataclass
class ProductImageImportResult:
    received: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    missing: list[str] | None = None
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.missing is None:
            self.missing = []
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return asdict(self)


def load_assignments(csv_path: Path) -> list[ProductImageAssignment]:
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing_columns:
            raise ValueError(f"CSV missing required columns: {', '.join(missing_columns)}")

        assignments: list[ProductImageAssignment] = []
        for row_number, row in enumerate(reader, start=2):
            sku = _clean(row.get("sku"))
            image_url = _clean(row.get("image_url"))
            if not sku or not image_url:
                raise ValueError(f"CSV row {row_number} must include sku and image_url")
            assignments.append(
                ProductImageAssignment(
                    sku=sku,
                    image_url=image_url,
                    category=_clean(row.get("category")),
                    subcategory=_clean(row.get("subcategory")),
                    name=_clean(row.get("name")),
                )
            )
    return assignments


async def apply_product_image_assignments(
    session: AsyncSession,
    assignments: list[ProductImageAssignment],
    *,
    dry_run: bool = False,
    fail_on_missing: bool = False,
) -> ProductImageImportResult:
    result = ProductImageImportResult(received=len(assignments))

    for assignment in assignments:
        query = (
            select(ProductORM, CategoryORM)
            .join(CategoryORM, ProductORM.category_id == CategoryORM.id)
            .where(ProductORM.sku == assignment.sku)
        )
        row = (await session.execute(query)).first()
        if row is None:
            result.skipped += 1
            result.missing.append(assignment.sku)
            continue

        product, category = row
        mismatch = _assignment_mismatch(product, category, assignment)
        if mismatch:
            result.skipped += 1
            result.errors.append(f"{assignment.sku}: {mismatch}")
            continue

        if _clean(product.image_url) == assignment.image_url:
            result.unchanged += 1
            continue

        if not dry_run:
            product.image_url = assignment.image_url
        result.updated += 1

    if fail_on_missing and result.missing:
        result.errors.append(f"Missing products: {', '.join(result.missing)}")

    if result.errors:
        await session.rollback()
    elif dry_run:
        await session.rollback()
    else:
        await session.commit()

    return result


def _assignment_mismatch(
    product: ProductORM,
    category: CategoryORM,
    assignment: ProductImageAssignment,
) -> str:
    if assignment.category and _normalize(category.slug) != _normalize(assignment.category):
        return f"category mismatch expected={assignment.category} actual={category.slug}"
    if assignment.subcategory and _normalize(product.subcategory) != _normalize(assignment.subcategory):
        return f"subcategory mismatch expected={assignment.subcategory} actual={product.subcategory}"
    if assignment.name and _normalize(product.name) != _normalize(assignment.name):
        return f"name mismatch expected={assignment.name} actual={product.name}"
    return ""


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _clean(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("-", " ").split())


async def _run(args: argparse.Namespace) -> int:
    assignments = load_assignments(Path(args.csv))
    async with AsyncSessionLocal() as session:
        result = await apply_product_image_assignments(
            session,
            assignments,
            dry_run=args.dry_run,
            fail_on_missing=args.fail_on_missing,
        )

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 1 if result.errors else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import product image URL assignments from CSV.")
    parser.add_argument("csv", help="Path to a CSV with sku,image_url columns.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report changes without committing.")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return a non-zero exit code if any SKU is not found.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_parse_args())))
