from app.application.catalog.image_sync import (
    ImageProduct,
    build_ecommerce_to_pos_image_candidates,
    normalize_image_url,
    pos_product_from_payload,
)
from scripts.compare_pos_ecommerce_images import (
    build_pos_products_query,
    compare_products,
    compare_sku,
)


def _product(sku: str, image_url: str = "https://cdn.test/image.webp") -> ImageProduct:
    return ImageProduct(
        sku=sku,
        product_name=f"Producto {sku}",
        category="sandwich",
        subcategory="Lomo",
        image_url=image_url,
    )


def test_normalize_image_url_strips_query_fragment_and_trailing_slash():
    assert normalize_image_url("https://cdn.test/image.webp?x=1#frag/") == "https://cdn.test/image.webp"


def test_compare_sku_statuses_for_image_differences():
    assert compare_sku("SKU", _product("SKU", "https://cdn.test/a.webp"), _product("SKU", "https://cdn.test/a.webp"))["status"] == "same_image"
    assert compare_sku("SKU", _product("SKU", ""), _product("SKU", ""))["status"] == "missing_in_both"
    assert compare_sku("SKU", _product("SKU", "https://cdn.test/a.webp"), _product("SKU", ""))["status"] == "missing_in_pos"
    assert compare_sku("SKU", _product("SKU", ""), _product("SKU", "https://cdn.test/a.webp"))["status"] == "missing_in_ecommerce"
    assert compare_sku("SKU", _product("SKU", "https://cdn.test/a.webp"), _product("SKU", "https://cdn.test/b.webp"))["status"] == "different_image"


def test_compare_products_reports_skus_missing_from_each_side():
    rows = compare_products(
        {"ECOM": _product("ECOM")},
        {"POS": _product("POS")},
    )
    by_sku = {row["sku"]: row for row in rows}

    assert by_sku["ECOM"]["status"] == "sku_not_found_in_pos"
    assert by_sku["POS"]["status"] == "sku_not_found_in_ecommerce"


def test_build_pos_products_query_uses_available_column_aliases():
    query = build_pos_products_query(
        "productos",
        {"id", "codigo", "nombre", "categoria", "subcategoria", "imagen_url"},
    )

    assert "`id` as pos_product_id" in query
    assert "`codigo` as sku" in query
    assert "`nombre` as product_name" in query
    assert "`imagen_url` as image_url" in query


def test_pos_product_from_payload_keeps_pos_product_id():
    product = pos_product_from_payload(
        {
            "id": 123,
            "sku": "SKU-1",
            "name": "Producto POS",
            "category": {"slug": "sandwich"},
            "subcategory": {"name": "Lomo"},
            "image_url": "",
        }
    )

    assert product.pos_product_id == "123"
    assert product.sku == "SKU-1"
    assert product.category == "sandwich"
    assert product.subcategory == "Lomo"


def test_build_ecommerce_to_pos_assignments_exports_only_missing_pos_images():
    ecommerce = {
        "SKU-1": _product("SKU-1", "https://cdn.test/sku-1.webp"),
        "SKU-2": _product("SKU-2", "https://cdn.test/sku-2.webp"),
        "SKU-3": _product("SKU-3", ""),
        "ECOM-ONLY": _product("ECOM-ONLY", "https://cdn.test/ecom-only.webp"),
    }
    pos = {
        "SKU-1": ImageProduct(
            sku="SKU-1",
            product_name="Producto POS 1",
            category="sandwich",
            subcategory="Lomo",
            image_url="",
            pos_product_id="10",
        ),
        "SKU-2": ImageProduct(
            sku="SKU-2",
            product_name="Producto POS 2",
            category="sandwich",
            subcategory="Lomo",
            image_url="https://cdn.test/sku-2.webp",
            pos_product_id="11",
        ),
        "SKU-3": ImageProduct(
            sku="SKU-3",
            product_name="Producto POS 3",
            category="sandwich",
            subcategory="Lomo",
            image_url="",
            pos_product_id="12",
        ),
        "POS-ONLY": _product("POS-ONLY", ""),
    }

    rows = build_ecommerce_to_pos_image_candidates(ecommerce, pos)

    assert rows == [
        {
            "sku": "SKU-1",
            "pos_product_id": "10",
            "name": "Producto POS 1",
            "category": "sandwich",
            "subcategory": "Lomo",
            "ecommerce_image_url": "https://cdn.test/sku-1.webp",
            "pos_current_image_url": "",
            "action": "update_pos_image_url",
        }
    ]
