from decimal import Decimal

from app.infrastructure.database.pos_catalog_sync import (
    _decimal_value,
    _extract_items,
)


def test_extract_items_accepts_direct_and_wrapped_payloads():
    assert _extract_items([{"sku": "P1"}, "bad"], "products") == [{"sku": "P1"}]
    assert _extract_items({"products": [{"sku": "P2"}]}, "products") == [{"sku": "P2"}]
    assert _extract_items({"catalog": {"products": [{"sku": "P3"}]}}, "products") == [{"sku": "P3"}]


def test_decimal_value_accepts_clp_price_formats():
    assert _decimal_value({"price": "$10.000"}, "price") == Decimal("10000")
    assert _decimal_value({"price": "10000"}, "price") == Decimal("10000")
    assert _decimal_value({"price": "10000,50"}, "price") == Decimal("10000.50")
