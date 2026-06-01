from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.catalog.image_assignments import (
    ProductImageAssignment,
    ProductImageImportResult,
    _assignment_mismatch,
    apply_product_image_assignments,
    load_assignments,
)
from app.infrastructure.database.session import AsyncSessionLocal


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
