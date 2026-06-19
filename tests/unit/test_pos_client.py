import json

import httpx
import pytest

from app.infrastructure.clients import PosClient, PosClientError


@pytest.mark.asyncio
async def test_pos_client_sends_internal_token_and_returns_summary():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/external/catalog/summary"
        assert request.headers["X-Internal-Token"] == "secret-token"
        return httpx.Response(200, json={"products": 10, "branches": 2})

    client = PosClient(
        base_url="https://pos.test",
        internal_token="secret-token",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )

    payload = await client.get_catalog_summary()

    assert payload == {"products": 10, "branches": 2}


@pytest.mark.asyncio
async def test_pos_client_maps_unauthorized_to_token_error():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid token"})

    client = PosClient(
        base_url="https://pos.test",
        internal_token="secret-token",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PosClientError) as exc_info:
        await client.get_catalog_summary()

    assert exc_info.value.status_code == 401
    assert exc_info.value.provider_status_code == 401
    assert "token" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_pos_client_maps_network_errors_to_bad_gateway():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = PosClient(
        base_url="https://pos.test",
        internal_token="secret-token",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PosClientError) as exc_info:
        await client.get_catalog_summary()

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_pos_client_sends_ecommerce_order_and_fetches_tracking():
    seen_paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers["X-Internal-Token"] == "secret-token"
        if request.method == "POST":
            assert request.url.path == "/api/internal/ecommerce/orders/"
            assert json.loads(request.content)["external_order_id"] == "order-1"
            return httpx.Response(200, json={"accepted": True, "pos_sale_id": "SALE-1"})
        assert request.url.path == "/api/internal/ecommerce/orders/order-1/"
        return httpx.Response(200, json={"status": "preparing"})

    client = PosClient(
        base_url="https://pos.test",
        internal_token="secret-token",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )

    sent = await client.send_order_to_pos({"external_order_id": "order-1"})
    tracking = await client.get_pos_order_tracking("order-1")

    assert sent == {"accepted": True, "pos_sale_id": "SALE-1"}
    assert tracking == {"status": "preparing"}
    assert seen_paths == ["/api/internal/ecommerce/orders/", "/api/internal/ecommerce/orders/order-1/"]


@pytest.mark.asyncio
async def test_pos_client_does_not_expose_internal_token_in_error_message():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "token secret-token invalid"})

    client = PosClient(
        base_url="https://pos.test",
        internal_token="secret-token",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PosClientError) as exc_info:
        await client.send_order_to_pos({"external_order_id": "order-1"})

    assert "secret-token" not in exc_info.value.message
    assert "***" in exc_info.value.message
