from app.infrastructure.database.dev_seed import (
    CATEGORY_SEEDS,
    MODIFIER_GROUP_SEEDS,
    MODIFIER_OPTION_SEEDS,
    PRODUCT_SEEDS,
)


def test_dev_seed_definitions_are_unique_for_idempotent_upserts():
    category_slugs = [seed.slug for seed in CATEGORY_SEEDS]
    product_slugs = [seed.slug for seed in PRODUCT_SEEDS]
    product_skus = [seed.sku for seed in PRODUCT_SEEDS]

    assert len(category_slugs) == len(set(category_slugs))
    assert len(product_slugs) == len(set(product_slugs))
    assert len(product_skus) == len(set(product_skus))


def test_dev_seed_contains_configurable_product_with_valid_relations():
    product_slugs = {seed.slug for seed in PRODUCT_SEEDS}
    category_slugs = {seed.slug for seed in CATEGORY_SEEDS}

    assert any(seed.category_slug in category_slugs for seed in PRODUCT_SEEDS)
    assert any(group.product_slug in product_slugs for group in MODIFIER_GROUP_SEEDS)
    assert any(option.product_slug in product_slugs for option in MODIFIER_OPTION_SEEDS)
    assert any(group.is_required for group in MODIFIER_GROUP_SEEDS)
