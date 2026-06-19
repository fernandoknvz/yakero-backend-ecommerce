from __future__ import annotations

import asyncio
import csv
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM
from app.infrastructure.database.session import AsyncSessionLocal


CDN_BASE_URL_ENV = "CDN_BASE_URL"
DEFAULT_CDN_BASE_URL = "https://cdn.yakero.cl"
EXPORTS_DIR = ROOT / "exports"
IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
R2_REQUIRED_ENV = ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
CATALOG_FAMILIES = {
    "ass",
    "bebidas",
    "casera",
    "churrasco",
    "empanadas",
    "extras",
    "gohan",
    "lomos",
    "lomo",
    "papas",
    "poke",
    "promociones",
    "salsas",
    "sandwich",
    "sushi",
}
GENERIC_TOKENS = {"image", "img", "foto", "producto", "products"}


@dataclass(frozen=True)
class CatalogProduct:
    sku: str
    name: str
    category: str
    category_slug: str
    subcategory: str
    price: str
    active: bool
    available_for_ecommerce: bool
    image_url: str


@dataclass(frozen=True)
class R2Image:
    cdn_path: str
    public_url: str
    folder: str
    filename: str
    extension: str
    possible_category: str


def normalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", clean(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value.lower()).split())


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_valid_image_url(value: object) -> bool:
    parsed = urlparse(clean(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def cdn_path_from_url(image_url: str, cdn_base_url: str) -> str:
    image_url = clean(image_url).split("?", 1)[0].split("#", 1)[0]
    base = cdn_base_url.rstrip("/") + "/"
    if not image_url.startswith(base):
        return ""
    return image_url[len(base) :].lstrip("/")


def public_url_for_path(cdn_path: str, cdn_base_url: str) -> str:
    return f"{cdn_base_url.rstrip('/')}/{cdn_path.lstrip('/')}"


def r2_image_from_key(key: str, cdn_base_url: str) -> R2Image | None:
    path = clean(key).lstrip("/")
    suffix = Path(path).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        return None
    folder = str(Path(path).parent).replace("\\", "/")
    if folder == ".":
        folder = ""
    filename = Path(path).name
    return R2Image(
        cdn_path=path,
        public_url=public_url_for_path(path, cdn_base_url),
        folder=folder,
        filename=filename,
        extension=suffix.lstrip("."),
        possible_category=possible_category_from_path(path),
    )


def possible_category_from_path(cdn_path: str) -> str:
    tokens = tokens_for(cdn_path)
    for family in CATALOG_FAMILIES:
        if family in tokens:
            return family
    parts = [part for part in Path(cdn_path).parts if part and part != "."]
    return parts[1] if len(parts) > 1 and parts[0] == "products" else (parts[0] if parts else "")


def tokens_for(*values: object) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(normalize_text(value).split())
    return {token for token in tokens if token and token not in GENERIC_TOKENS}


async def load_catalog_products() -> list[CatalogProduct]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ProductORM, CategoryORM)
            .join(CategoryORM, ProductORM.category_id == CategoryORM.id)
            .order_by(CategoryORM.slug, ProductORM.subcategory, ProductORM.name)
        )
        rows = result.all()

    products: list[CatalogProduct] = []
    for product, category in rows:
        is_available = bool(product.is_available)
        category_active = bool(category.is_active)
        products.append(
            CatalogProduct(
                sku=clean(product.sku),
                name=clean(product.name),
                category=clean(category.slug or category.name),
                category_slug=clean(category.slug),
                subcategory=clean(product.subcategory),
                price=format_price(product.price),
                active=is_available and category_active,
                available_for_ecommerce=is_available and category_active,
                image_url=clean(product.image_url),
            )
        )
    return products


def format_price(value: Any) -> str:
    if value is None:
        return ""
    decimal = Decimal(str(value))
    if decimal == decimal.to_integral_value():
        return str(decimal.quantize(Decimal("1")))
    return str(decimal)


def load_r2_images(cdn_base_url: str) -> list[R2Image]:
    config = r2_config_from_env()
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required to list Cloudflare R2 objects. Install it with: pip install boto3") from exc

    client = boto3.client(
        "s3",
        endpoint_url=config["R2_ENDPOINT_URL"],
        aws_access_key_id=config["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=config["R2_SECRET_ACCESS_KEY"],
    )
    paginator = client.get_paginator("list_objects_v2")
    images: list[R2Image] = []
    for page in paginator.paginate(Bucket=config["R2_BUCKET_NAME"]):
        for item in page.get("Contents", []):
            image = r2_image_from_key(item.get("Key", ""), cdn_base_url)
            if image is not None:
                images.append(image)
    return sorted(images, key=lambda image: image.cdn_path)


def r2_config_from_env() -> dict[str, str]:
    missing = [name for name in R2_REQUIRED_ENV if not clean(os.getenv(name))]
    if missing:
        raise RuntimeError(
            "Missing R2 environment variables: "
            + ", ".join(missing)
            + ". Required: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME."
        )
    return {name: clean(os.getenv(name)) for name in R2_REQUIRED_ENV}


def build_products_without_images(products: list[CatalogProduct]) -> list[dict[str, Any]]:
    rows = []
    for product in products:
        if not product.available_for_ecommerce or is_valid_image_url(product.image_url):
            continue
        rows.append(
            {
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "subcategory": product.subcategory,
                "price": product.price,
                "active": product.active,
                "available_for_ecommerce": product.available_for_ecommerce,
            }
        )
    return rows


def build_images_used(products: list[CatalogProduct], cdn_base_url: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[CatalogProduct]] = {}
    for product in products:
        if not is_valid_image_url(product.image_url):
            continue
        image_url = product.image_url.split("?", 1)[0].split("#", 1)[0]
        grouped.setdefault(image_url, []).append(product)

    rows = []
    for image_url, group in sorted(grouped.items()):
        rows.append(
            {
                "image_url": image_url,
                "cdn_path": cdn_path_from_url(image_url, cdn_base_url),
                "usage_count": len(group),
                "skus": join_unique(product.sku for product in group),
                "product_names": join_unique(product.name for product in group),
                "categories": join_unique(product.category for product in group),
                "subcategories": join_unique(product.subcategory for product in group),
            }
        )
    return rows


def build_images_unused(r2_images: list[R2Image], used_cdn_paths: set[str]) -> list[dict[str, Any]]:
    rows = []
    for image in r2_images:
        if image.cdn_path in used_cdn_paths:
            continue
        rows.append(
            {
                "cdn_path": image.cdn_path,
                "public_url": image.public_url,
                "folder": image.folder,
                "filename": image.filename,
                "extension": image.extension,
                "possible_category": image.possible_category,
                "reason": "not referenced by any product image_url",
            }
        )
    return rows


def build_reusable_image_candidates(
    products_without_images: list[CatalogProduct],
    r2_images: list[R2Image],
) -> list[dict[str, Any]]:
    rows = []
    for product in products_without_images:
        scored = []
        for image in r2_images:
            confidence, reason = score_candidate(product, image)
            if confidence >= 35:
                scored.append((confidence, reason, image))
        for confidence, reason, image in sorted(scored, key=lambda item: (-item[0], item[2].cdn_path))[:3]:
            rows.append(
                {
                    "sku": product.sku,
                    "product_name": product.name,
                    "category": product.category,
                    "subcategory": product.subcategory,
                    "candidate_cdn_path": image.cdn_path,
                    "candidate_public_url": image.public_url,
                    "confidence": confidence,
                    "match_reason": reason,
                }
            )
    return rows


def score_candidate(product: CatalogProduct, image: R2Image) -> tuple[int, str]:
    product_tokens = tokens_for(product.sku, product.name, product.category, product.subcategory)
    image_tokens = tokens_for(image.cdn_path, image.folder, image.filename)
    shared = product_tokens & image_tokens
    product_family = product_tokens & CATALOG_FAMILIES
    image_family = image_tokens & CATALOG_FAMILIES
    reasons = []
    score = 0

    if shared:
        shared_score = min(len(shared) * 12, 36)
        score += shared_score
        reasons.append("shared tokens: " + ", ".join(sorted(shared)))

    category = normalize_text(product.category)
    subcategory = normalize_text(product.subcategory)
    image_text = normalize_text(f"{image.folder} {image.filename}")
    if category and category in image_text:
        score += 20
        reasons.append("category appears in CDN path")
    if subcategory and subcategory in image_text:
        score += 24
        reasons.append("subcategory appears in CDN path")
    if product_family and product_family & image_family:
        score += 20
        reasons.append("same catalog family")

    name_tokens = tokens_for(product.name)
    filename_tokens = tokens_for(Path(image.filename).stem)
    name_overlap = name_tokens & filename_tokens
    if name_overlap:
        score += min(len(name_overlap) * 10, 20)
        reasons.append("product name matches filename")

    return min(score, 100), "; ".join(reasons) or "low text similarity"


def build_duplicate_image_candidates(r2_images: list[R2Image]) -> list[dict[str, Any]]:
    groups: dict[str, list[R2Image]] = {}
    for image in r2_images:
        stem = Path(image.filename).stem
        compact_key = "".join(tokens_for(stem))
        if compact_key:
            groups.setdefault(f"filename:{compact_key}", []).append(image)

        meaningful = [token for token in normalize_text(f"{image.folder} {stem}").split() if token not in GENERIC_TOKENS]
        family_tokens = [token for token in meaningful if token in CATALOG_FAMILIES]
        if family_tokens and len(meaningful) >= 2:
            groups.setdefault(f"family:{family_tokens[0]}:{'-'.join(meaningful[:3])}", []).append(image)

    rows = []
    seen_paths: set[tuple[str, ...]] = set()
    for group_key, images in sorted(groups.items()):
        unique_images = sorted({image.cdn_path: image for image in images}.values(), key=lambda image: image.cdn_path)
        if len(unique_images) < 2:
            continue
        paths_key = tuple(image.cdn_path for image in unique_images)
        if paths_key in seen_paths:
            continue
        seen_paths.add(paths_key)
        reason = "same normalized filename" if group_key.startswith("filename:") else "same family or path prefix"
        rows.append(
            {
                "group_key": group_key,
                "cdn_paths": join_unique(image.cdn_path for image in unique_images),
                "public_urls": join_unique(image.public_url for image in unique_images),
                "filenames": join_unique(image.filename for image in unique_images),
                "reason": reason,
                "suggested_action": "review manually before deleting or consolidating",
            }
        )
    return rows


def join_unique(values) -> str:
    return " | ".join(sorted({clean(value) for value in values if clean(value)}))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


async def main() -> int:
    cdn_base_url = clean(os.getenv(CDN_BASE_URL_ENV)) or DEFAULT_CDN_BASE_URL
    r2_images = load_r2_images(cdn_base_url)
    products = await load_catalog_products()
    active_without_images = [product for product in products if product.available_for_ecommerce and not is_valid_image_url(product.image_url)]

    products_without_images = build_products_without_images(products)
    images_used = build_images_used(products, cdn_base_url)
    used_cdn_paths = {row["cdn_path"] for row in images_used if row["cdn_path"]}
    images_unused = build_images_unused(r2_images, used_cdn_paths)
    reusable_candidates = build_reusable_image_candidates(active_without_images, r2_images)
    duplicate_candidates = build_duplicate_image_candidates(r2_images)

    write_csv(
        EXPORTS_DIR / "products_without_images.csv",
        ["sku", "name", "category", "subcategory", "price", "active", "available_for_ecommerce"],
        products_without_images,
    )
    write_csv(
        EXPORTS_DIR / "images_used.csv",
        ["image_url", "cdn_path", "usage_count", "skus", "product_names", "categories", "subcategories"],
        images_used,
    )
    write_csv(
        EXPORTS_DIR / "images_unused.csv",
        ["cdn_path", "public_url", "folder", "filename", "extension", "possible_category", "reason"],
        images_unused,
    )
    write_csv(
        EXPORTS_DIR / "reusable_image_candidates.csv",
        [
            "sku",
            "product_name",
            "category",
            "subcategory",
            "candidate_cdn_path",
            "candidate_public_url",
            "confidence",
            "match_reason",
        ],
        reusable_candidates,
    )
    write_csv(
        EXPORTS_DIR / "duplicate_image_candidates.csv",
        ["group_key", "cdn_paths", "public_urls", "filenames", "reason", "suggested_action"],
        duplicate_candidates,
    )

    print("Catalog image audit finished.")
    print(f"- total productos: {len(products)}")
    print(f"- productos con imagen: {sum(1 for product in products if is_valid_image_url(product.image_url))}")
    print(f"- productos sin imagen: {len(products_without_images)}")
    print(f"- total imagenes R2: {len(r2_images)}")
    print(f"- imagenes usadas: {len(used_cdn_paths)}")
    print(f"- imagenes no usadas: {len(images_unused)}")
    print(f"- candidatos reutilizables: {len(reusable_candidates)}")
    print(f"- candidatos duplicados: {len(duplicate_candidates)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
