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
