from __future__ import annotations

import pytest

from tests.unit.test_pos_order_sync import _checkout_session, _order

from app.infrastructure.api.routers import orders as orders_router


class FakeOrderRepository:
    def __init__(self, _db):
        pass

    async def get_by_id(self, order_id):
        order = _order()
        order.id = order_id
        return order


class FakeCheckoutRepository:
    def __init__(self, _db):
        pass

    async def get_by_created_order_id(self, order_id):
        session = _checkout_session()
        session.created_order_id = order_id
        return session


class FakeCatalogRepository:
    def __init__(self, _db):
        pass


class FakePosClient:
    called_external_order_id = None

    async def get_pos_order_tracking(self, external_order_id):
        FakePosClient.called_external_order_id = external_order_id
        return {"status": "preparing", "pos_sale_id": "SALE-1"}


@pytest.mark.asyncio
async def test_order_tracking_endpoint_queries_pos_with_external_reference(monkeypatch):
    monkeypatch.setattr(orders_router, "SQLOrderRepository", FakeOrderRepository)
    monkeypatch.setattr(orders_router, "SQLCheckoutSessionRepository", FakeCheckoutRepository)
    monkeypatch.setattr(orders_router, "SQLProductRepository", FakeCatalogRepository)
    monkeypatch.setattr(orders_router, "SQLPromotionRepository", FakeCatalogRepository)
    monkeypatch.setattr(orders_router, "PosClient", FakePosClient)

    response = await orders_router.get_order_tracking(order_id=1, db=None, current_user=None)

    assert response.external_order_id == "checkout-ref"
    assert FakePosClient.called_external_order_id == "checkout-ref"
    assert response.pos == {"status": "preparing", "pos_sale_id": "SALE-1"}
