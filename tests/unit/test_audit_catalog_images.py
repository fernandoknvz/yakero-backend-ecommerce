from scripts.audit_catalog_images import (
    CatalogProduct,
    build_duplicate_image_candidates,
    build_images_unused,
    build_reusable_image_candidates,
    cdn_path_from_url,
    is_valid_image_url,
    normalize_text,
    r2_image_from_key,
)


CDN_BASE_URL = "https://cdn.yakero.cl"


def test_normalize_text_removes_accents_symbols_and_extra_spaces():
    assert normalize_text("  Lomo Luco, Champiñón!! ") == "lomo luco champinon"


def test_cdn_path_from_url_only_accepts_configured_cdn_base():
    assert (
        cdn_path_from_url(
            "https://cdn.yakero.cl/products/sandwich/image.webp?cache=1",
            CDN_BASE_URL,
        )
        == "products/sandwich/image.webp"
    )
    assert cdn_path_from_url("https://img.test/image.webp", CDN_BASE_URL) == ""


def test_is_valid_image_url_requires_http_url():
    assert is_valid_image_url("https://cdn.yakero.cl/products/image.webp") is True
    assert is_valid_image_url("") is False
    assert is_valid_image_url("products/image.webp") is False


def test_build_images_unused_compares_r2_paths_with_used_cdn_paths():
    used = {"products/sandwich/sandwich-lomo/sandwich-lomo.webp"}
    images = [
        r2_image_from_key("products/sandwich/sandwich-lomo/sandwich-lomo.webp", CDN_BASE_URL),
        r2_image_from_key("products/sandwich/sandwich-lomo/sandwich-lomo-luco.webp", CDN_BASE_URL),
    ]

    rows = build_images_unused([image for image in images if image], used)

    assert len(rows) == 1
    assert rows[0]["cdn_path"] == "products/sandwich/sandwich-lomo/sandwich-lomo-luco.webp"
    assert rows[0]["reason"] == "not referenced by any product image_url"


def test_build_reusable_image_candidates_scores_text_matches():
    product = CatalogProduct(
        sku="SAND-CHUR-BAR-LUC",
        name="Churrasco Barros Luco",
        category="sandwich",
        category_slug="sandwich",
        subcategory="Churrasco",
        price="5000",
        active=True,
        available_for_ecommerce=True,
        image_url="",
    )
    image = r2_image_from_key(
        "products/sandwich/sandwich-churrasco/sandwich-churrasco-luco.webp",
        CDN_BASE_URL,
    )

    rows = build_reusable_image_candidates([product], [image])

    assert len(rows) == 1
    assert rows[0]["sku"] == "SAND-CHUR-BAR-LUC"
    assert rows[0]["candidate_cdn_path"].endswith("sandwich-churrasco-luco.webp")
    assert rows[0]["confidence"] >= 35
    assert "shared tokens" in rows[0]["match_reason"]


def test_build_duplicate_image_candidates_groups_normalized_filenames():
    images = [
        r2_image_from_key("products/sandwich/Lomo Luco.webp", CDN_BASE_URL),
        r2_image_from_key("products/sandwich/lomo-luco.webp", CDN_BASE_URL),
        r2_image_from_key("products/sandwich/chacarero.webp", CDN_BASE_URL),
    ]

    rows = build_duplicate_image_candidates([image for image in images if image])

    assert any("Lomo Luco.webp" in row["filenames"] for row in rows)
    assert any("lomo-luco.webp" in row["filenames"] for row in rows)
