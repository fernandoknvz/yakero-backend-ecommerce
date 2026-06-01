from __future__ import annotations

from dataclasses import dataclass
from typing import Any


IMAGE_KEYS = (
    "image_url",
    "imagen_url",
    "imagen",
    "image",
    "photo_url",
    "picture",
    "thumbnail_url",
    "media_url",
)


@dataclass(frozen=True)
class ImageProduct:
    sku: str
    product_name: str
    category: str
    subcategory: str
    image_url: str
    pos_product_id: str = ""


def build_ecommerce_to_pos_image_candidates(
    ecommerce_products: dict[str, ImageProduct],
    pos_products: dict[str, ImageProduct],
) -> list[dict[str, str]]:
    rows = []
    for sku in sorted(set(ecommerce_products) & set(pos_products)):
        ecommerce = ecommerce_products[sku]
        pos = pos_products[sku]
        if not has_image(ecommerce.image_url) or has_image(pos.image_url):
            continue
        rows.append(
            {
                "sku": sku,
                "pos_product_id": pos.pos_product_id,
                "name": pos.product_name or ecommerce.product_name,
                "category": pos.category or ecommerce.category,
                "subcategory": pos.subcategory or ecommerce.subcategory,
                "ecommerce_image_url": ecommerce.image_url,
                "pos_current_image_url": pos.image_url,
                "action": "update_pos_image_url",
            }
        )
    return rows


def pos_product_from_payload(raw: dict[str, Any]) -> ImageProduct:
    category = raw.get("category") or raw.get("categoria")
    category_name = ""
    if isinstance(category, dict):
        category_name = first_string(category, "slug", "code", "external_code", "name", "nombre", "title")
    else:
        category_name = first_string(raw, "category_slug", "categoria_slug", "category", "categoria", "category_name")

    subcategory = raw.get("subcategory") or raw.get("sub_category") or raw.get("subcategoria")
    if isinstance(subcategory, dict):
        subcategory_name = first_string(subcategory, "name", "nombre", "title", "slug", "code")
    else:
        subcategory_name = first_string(raw, "subcategory", "sub_category", "subcategoria")

    return ImageProduct(
        sku=first_string(raw, "sku", "SKU", "code", "codigo", "external_code"),
        product_name=first_string(raw, "name", "nombre", "title", "titulo"),
        category=category_name,
        subcategory=subcategory_name,
        image_url=first_string(raw, *IMAGE_KEYS),
        pos_product_id=first_string(raw, "id", "product_id", "pos_product_id", "external_id"),
    )


def normalize_image_url(value: object) -> str:
    return clean(value).split("?", 1)[0].split("#", 1)[0].rstrip("/")


def has_image(value: object) -> bool:
    return bool(normalize_image_url(value))


def first_string(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in raw and raw[key] is not None and raw[key] != "":
            return clean(raw[key])
    return ""


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
