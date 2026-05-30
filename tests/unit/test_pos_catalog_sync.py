from decimal import Decimal

import pytest

from app.domain.models.enums import TicketTag
from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM, PromotionORM
from app.infrastructure.database.pos_catalog_sync import (
    PosCatalogSyncService,
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
    def __init__(self):
        self.categories = []
        self.products = []
        self.promotions = []
        self.flushes = 0

    def add(self, instance):
        if isinstance(instance, CategoryORM):
            self.categories.append(instance)
        elif isinstance(instance, ProductORM):
            self.products.append(instance)
        elif isinstance(instance, PromotionORM):
            self.promotions.append(instance)

    async def flush(self):
        self.flushes += 1
        for index, category in enumerate(self.categories, start=1):
            if category.id is None:
                category.id = index

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is CategoryORM:
            return _ExecuteResult(self.categories)
        if entity is ProductORM:
            return _ExecuteResult(self.products)
        if entity is PromotionORM:
            return _ExecuteResult(self.promotions)
        return _ExecuteResult([])


class FakePosClient:
    def __init__(self, *, products, promotions=None, branches=None):
        self._products = products
        self._promotions = promotions or []
        self._branches = branches or []

    async def get_products(self):
        return {"products": self._products}

    async def get_promotions(self):
        return {"promotions": self._promotions}

    async def get_branches(self):
        return {"branches": self._branches}


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
        "name": "Roll antiguo",
        "slug": "roll-antiguo-sku-1",
        "description": "Antes",
        "price": Decimal("1000"),
        "image_url": None,
        "ticket_tag": TicketTag.COCINA_SUSHI,
        "is_available": True,
        "sort_order": 1,
    }
    values.update(overrides)
    return ProductORM(**values)


def _promotion(**overrides):
    values = {
        "external_code": "PROMO-1",
        "name": "Promo antigua",
        "description": "Antes",
        "promotion_type": "bundle",
        "value": Decimal("5000"),
        "image_url": None,
        "is_active": True,
        "starts_at": None,
        "ends_at": None,
    }
    values.update(overrides)
    return PromotionORM(**values)


def _raw_product(**overrides):
    values = {
        "sku": "SKU-1",
        "name": "Roll actualizado",
        "description": "Ahora",
        "price": "2500",
        "subcategory": "Hand Rolls",
        "image_url": "https://img.test/roll.png",
        "category": {
            "name": "Rolls",
            "slug": "rolls",
            "kitchen_destination": "sushi",
        },
        "available_for_ecommerce": True,
        "kitchen_destination": "sushi",
        "sort_order": 3,
    }
    values.update(overrides)
    return values


def _raw_promotion(**overrides):
    values = {
        "external_code": "PROMO-1",
        "name": "Promo actualizada",
        "description": "Ahora",
        "promotion_type": "bundle",
        "value": "8990",
        "image_url": "https://img.test/promo.png",
        "available_for_ecommerce": True,
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_pos_catalog_sync_upserts_products_and_deactivates_missing_skus():
    session = FakeSession()
    session.categories.append(_category())
    existing = _product()
    missing_from_pos = _product(sku="SKU-OLD", slug="old", name="Producto viejo")
    session.products.extend([existing, missing_from_pos])
    client = FakePosClient(
        products=[
            _raw_product(),
            _raw_product(sku="SKU-2", name="Nuevo roll"),
        ],
        branches=[{"id": "BR-1", "name": "Sucursal"}],
    )

    result = await PosCatalogSyncService(session, client).sync()

    assert result.products.received == 2
    assert result.products.created == 1
    assert result.products.updated == 1
    assert result.products.deactivated == 1
    assert result.branches.received == 1
    assert len(session.products) == 3
    assert existing.name == "Roll actualizado"
    assert existing.price == Decimal("2500")
    assert existing.subcategory == "Hand Rolls"
    assert missing_from_pos.is_available is False


@pytest.mark.asyncio
async def test_pos_catalog_sync_does_not_duplicate_products_on_repeated_sync():
    session = FakeSession()
    session.categories.append(_category())
    client = FakePosClient(products=[_raw_product()])
    service = PosCatalogSyncService(session, client)

    first = await service.sync()
    second = await service.sync()

    assert first.products.created == 1
    assert second.products.created == 0
    assert second.products.updated == 1
    assert [product.sku for product in session.products] == ["SKU-1"]


@pytest.mark.asyncio
async def test_pos_catalog_sync_updates_existing_product_by_sku():
    session = FakeSession()
    session.categories.append(_category())
    product = _product(sku="SKU-123", name="Antes", price=Decimal("1000"))
    session.products.append(product)
    client = FakePosClient(
        products=[
            _raw_product(
                sku="SKU-123",
                name="Despues",
                price="3990",
                image_url="https://img.test/new.png",
            )
        ]
    )

    result = await PosCatalogSyncService(session, client).sync()

    assert result.products.created == 0
    assert result.products.updated == 1
    assert product.name == "Despues"
    assert product.price == Decimal("3990")
    assert product.subcategory == "Hand Rolls"
    assert product.image_url == "https://img.test/new.png"


@pytest.mark.asyncio
async def test_pos_catalog_sync_saves_subcategory_aliases():
    session = FakeSession()
    session.categories.append(_category())
    client = FakePosClient(
        products=[
            _raw_product(sku="SKU-SUB", subcategory={"name": "Papas Fritas"}),
            _raw_product(sku="SKU-SUB-2", subcategory="", sub_category="Empanadas"),
        ]
    )

    await PosCatalogSyncService(session, client).sync()

    by_sku = {product.sku: product for product in session.products}
    assert by_sku["SKU-SUB"].subcategory == "Papas Fritas"
    assert by_sku["SKU-SUB-2"].subcategory == "Empanadas"


@pytest.mark.asyncio
async def test_pos_catalog_sync_marks_unavailable_product_inactive():
    session = FakeSession()
    session.categories.append(_category())
    product = _product(sku="SKU-1", is_available=True)
    session.products.append(product)
    client = FakePosClient(products=[_raw_product(available_for_ecommerce=False)])

    result = await PosCatalogSyncService(session, client).sync()

    assert result.products.deactivated == 1
    assert product.is_available is False


@pytest.mark.asyncio
async def test_pos_catalog_sync_preserves_existing_product_image_when_pos_image_is_empty():
    session = FakeSession()
    session.categories.append(_category())
    product = _product(image_url="https://img.test/existing.png")
    session.products.append(product)
    client = FakePosClient(products=[_raw_product(image_url="")])

    await PosCatalogSyncService(session, client).sync()

    assert product.image_url == "https://img.test/existing.png"


@pytest.mark.asyncio
async def test_pos_catalog_sync_updates_existing_product_image_when_pos_sends_new_url():
    session = FakeSession()
    session.categories.append(_category())
    product = _product(image_url="https://img.test/existing.png")
    session.products.append(product)
    client = FakePosClient(products=[_raw_product(image_url="https://img.test/new-product.png")])

    await PosCatalogSyncService(session, client).sync()

    assert product.image_url == "https://img.test/new-product.png"


@pytest.mark.asyncio
async def test_pos_catalog_sync_new_product_without_image_stays_without_image():
    session = FakeSession()
    session.categories.append(_category())
    client = FakePosClient(products=[_raw_product(sku="SKU-NEW", image_url="")])

    await PosCatalogSyncService(session, client).sync()

    created = next(product for product in session.products if product.sku == "SKU-NEW")
    assert created.image_url == ""


@pytest.mark.asyncio
async def test_pos_catalog_sync_preserves_existing_promotion_image_when_pos_image_is_empty():
    session = FakeSession()
    promotion = _promotion(image_url="https://img.test/existing-promo.png")
    session.promotions.append(promotion)
    client = FakePosClient(products=[], promotions=[_raw_promotion(image_url="")])

    await PosCatalogSyncService(session, client).sync()

    assert promotion.image_url == "https://img.test/existing-promo.png"


@pytest.mark.asyncio
async def test_pos_catalog_sync_updates_existing_promotion_image_when_pos_sends_new_url():
    session = FakeSession()
    promotion = _promotion(image_url="https://img.test/existing-promo.png")
    session.promotions.append(promotion)
    client = FakePosClient(
        products=[],
        promotions=[_raw_promotion(image_url="https://img.test/new-promo.png")],
    )

    await PosCatalogSyncService(session, client).sync()

    assert promotion.image_url == "https://img.test/new-promo.png"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alias", "url"),
    [
        ("imagen_url", "https://img.test/imagen-url.png"),
        ("imagen", "https://img.test/imagen.png"),
        ("thumbnail_url", "https://img.test/thumb.png"),
        ("media_url", "https://img.test/media.png"),
    ],
)
async def test_pos_catalog_sync_recognizes_product_image_aliases(alias, url):
    session = FakeSession()
    session.categories.append(_category())
    raw = _raw_product(sku=f"SKU-{alias}", image_url="")
    raw[alias] = url
    client = FakePosClient(products=[raw])

    await PosCatalogSyncService(session, client).sync()

    created = next(product for product in session.products if product.sku == f"SKU-{alias}")
    assert created.image_url == url


@pytest.mark.asyncio
async def test_pos_catalog_sync_recognizes_promotion_and_category_image_aliases():
    session = FakeSession()
    category = _category(image_url="https://img.test/old-category.png")
    session.categories.append(category)
    promotion = _promotion(image_url="https://img.test/old-promo.png")
    session.promotions.append(promotion)
    raw_product = _raw_product(image_url="")
    raw_product["category"] = {
        "name": "Rolls",
        "slug": "rolls",
        "media_url": "https://img.test/category-media.png",
    }
    raw_promotion = _raw_promotion(image_url="", thumbnail_url="https://img.test/promo-thumb.png")
    client = FakePosClient(products=[raw_product], promotions=[raw_promotion])

    await PosCatalogSyncService(session, client).sync()

    assert category.image_url == "https://img.test/category-media.png"
    assert promotion.image_url == "https://img.test/promo-thumb.png"
