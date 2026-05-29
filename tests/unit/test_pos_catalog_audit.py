from decimal import Decimal

import pytest

from app.domain.models.enums import TicketTag
from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM, PromotionORM
from app.infrastructure.database.pos_catalog_audit import PosCatalogAuditService


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class FakeSession:
    def __init__(self, *, categories=None, products=None, promotions=None):
        self.categories = categories or []
        self.products = products or []
        self.promotions = promotions or []

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is CategoryORM:
            return _ExecuteResult(self.categories)
        if entity is ProductORM:
            return _ExecuteResult(self.products)
        if entity is PromotionORM:
            return _ExecuteResult(self.promotions)
        return _ExecuteResult([])


def _category(**overrides):
    values = {
        "id": 1,
        "name": "Rolls",
        "slug": "rolls",
        "ticket_tag": TicketTag.COCINA_SUSHI,
        "image_url": None,
        "sort_order": 1,
        "is_active": True,
    }
    values.update(overrides)
    return CategoryORM(**values)


def _product(**overrides):
    values = {
        "category_id": 1,
        "sku": "SKU-1",
        "name": "Roll",
        "slug": "roll-sku-1",
        "description": None,
        "price": Decimal("2500"),
        "image_url": "https://img.test/roll.png",
        "ticket_tag": TicketTag.COCINA_SUSHI,
        "is_available": True,
        "sort_order": 1,
    }
    values.update(overrides)
    return ProductORM(**values)


def _promotion(**overrides):
    values = {
        "external_code": "PROMO-1",
        "name": "Promo",
        "description": None,
        "promotion_type": "bundle",
        "value": Decimal("9990"),
        "image_url": "https://img.test/promo.png",
        "is_active": True,
        "starts_at": None,
        "ends_at": None,
    }
    values.update(overrides)
    return PromotionORM(**values)


@pytest.mark.asyncio
async def test_pos_catalog_audit_returns_expected_counts():
    session = FakeSession(
        categories=[_category(), _category(id=2, name="Bebidas", slug="bebidas", ticket_tag=TicketTag.CAJA)],
        products=[
            _product(sku="SKU-1"),
            _product(sku="SKU-2", is_available=False),
            _product(sku="", category_id=99, price=Decimal("0"), image_url=None),
        ],
        promotions=[
            _promotion(external_code="PROMO-1"),
            _promotion(external_code="", value=Decimal("0"), image_url=None, is_active=False),
        ],
    )

    payload = await PosCatalogAuditService(session).audit()

    assert payload["ok"] is True
    assert payload["products"]["total"] == 3
    assert payload["products"]["active"] == 2
    assert payload["products"]["available_for_ecommerce"] == 2
    assert payload["products"]["without_price"] == 1
    assert payload["products"]["without_category"] == 1
    assert payload["products"]["without_sku"] == 1
    assert payload["products"]["without_image"] == 1
    assert payload["promotions"]["total"] == 2
    assert payload["promotions"]["active"] == 1
    assert payload["promotions"]["without_price"] == 1
    assert payload["promotions"]["without_code"] == 1
    assert payload["promotions"]["without_image"] == 1
    assert payload["categories"] == {"total": 2, "names": ["Bebidas", "Rolls"]}
    assert payload["branches"] == {"total": 0, "active": 0}


@pytest.mark.asyncio
async def test_pos_catalog_audit_detects_products_without_image():
    session = FakeSession(categories=[_category()], products=[_product(image_url=" ")])

    payload = await PosCatalogAuditService(session).audit()

    assert payload["products"]["without_image"] == 1


@pytest.mark.asyncio
async def test_pos_catalog_audit_detects_products_without_price():
    session = FakeSession(categories=[_category()], products=[_product(price=Decimal("0"))])

    payload = await PosCatalogAuditService(session).audit()

    assert payload["products"]["without_price"] == 1


@pytest.mark.asyncio
async def test_pos_catalog_audit_detects_duplicate_skus():
    session = FakeSession(
        categories=[_category()],
        products=[
            _product(sku="DUP-1", slug="dup-1"),
            _product(sku="DUP-1", slug="dup-2"),
            _product(sku="OK-1", slug="ok-1"),
        ],
    )

    payload = await PosCatalogAuditService(session).audit()

    assert payload["products"]["duplicate_skus"] == ["DUP-1"]


@pytest.mark.asyncio
async def test_pos_catalog_audit_detects_promotions_without_image():
    session = FakeSession(promotions=[_promotion(image_url=None)])

    payload = await PosCatalogAuditService(session).audit()

    assert payload["promotions"]["without_image"] == 1
