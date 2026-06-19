from __future__ import annotations

import logging
from typing import Any

import httpx

from ...config import settings


logger = logging.getLogger(__name__)


class PosClientError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 502,
        provider_status_code: int | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.provider_status_code = provider_status_code
        super().__init__(message)


class PosClient:
    def __init__(
        self,
        base_url: str | None = None,
        internal_token: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        configured_base_url = base_url if base_url is not None else settings.resolved_pos_internal_base_url
        self._base_url = configured_base_url.rstrip("/")
        self._internal_token = internal_token if internal_token is not None else settings.pos_internal_token
        self._catalog_timeout = timeout if timeout is not None else settings.pos_catalog_timeout_seconds
        self._order_timeout = timeout if timeout is not None else settings.pos_order_timeout_seconds
        self._transport = transport

    async def get_catalog_summary(self) -> dict[str, Any]:
        return await self._get("/api/external/catalog/summary")

    async def get_products(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/products")

    async def get_promotions(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/promotions")

    async def get_branches(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/branches")

    async def send_order_to_pos(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/internal/ecommerce/orders/",
            timeout=self._order_timeout,
            json=payload,
        )

    async def get_pos_order_tracking(self, external_order_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/internal/ecommerce/orders/{external_order_id}/",
            timeout=self._order_timeout,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get(self, path: str) -> Any:
        return await self._request("GET", path, timeout=self._catalog_timeout)

    async def _request(self, method: str, path: str, timeout: float, **kwargs: Any) -> Any:
        self._ensure_configured()
        headers = {"X-Internal-Token": self._internal_token}

        logger.info(
            "POS request started method=%s url=%s header_names=%s token_configured=%s",
            method,
            self._full_url(path),
            list(headers.keys()),
            bool(self._internal_token),
        )
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            transport=self._transport,
        ) as client:
            try:
                response = await client.request(method, path, headers=headers, **kwargs)
                logger.info(
                    "POS response endpoint=%s status_code=%s",
                    path,
                    response.status_code,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "POS HTTP error endpoint=%s status_code=%s message=%s",
                    path,
                    status_code,
                    self._safe_error_message(exc),
                )
                if status_code in {401, 403}:
                    raise PosClientError(
                        "POS rejected internal token or configuration.",
                        status_code=status_code,
                        provider_status_code=status_code,
                    ) from exc
                response_payload = self._response_payload(exc.response)
                if status_code >= 500:
                    raise PosClientError(
                        self._response_error_message(response_payload)
                        or "POS unavailable or returned an upstream error.",
                        status_code=502,
                        provider_status_code=status_code,
                    ) from exc
                raise PosClientError(
                    self._response_error_message(response_payload)
                    or "POS request was rejected.",
                    status_code=502,
                    provider_status_code=status_code,
                ) from exc
            except httpx.TimeoutException as exc:
                logger.warning(
                    "POS timeout endpoint=%s exception_type=%s message=%s",
                    path,
                    type(exc).__name__,
                    self._safe_error_message(exc),
                )
                raise PosClientError("POS request timed out.", status_code=502) from exc
            except httpx.HTTPError as exc:
                logger.warning(
                    "POS network error endpoint=%s exception_type=%s message=%s",
                    path,
                    type(exc).__name__,
                    self._safe_error_message(exc),
                )
                raise PosClientError("POS unavailable or network error.", status_code=502) from exc

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("POS invalid JSON endpoint=%s", path)
            raise PosClientError("POS returned an invalid JSON response.", status_code=502) from exc

    def _ensure_configured(self) -> None:
        if not self._base_url:
            raise PosClientError("POS_INTERNAL_BASE_URL is not configured.", status_code=500)
        if not self._internal_token:
            raise PosClientError("POS_INTERNAL_TOKEN is not configured.", status_code=500)
        if self._catalog_timeout <= 0 or self._order_timeout <= 0:
            raise PosClientError("POS timeout must be greater than 0.", status_code=500)

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if self._internal_token:
            message = message.replace(self._internal_token, "***")
        return message

    def _full_url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _response_payload(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    def _response_error_message(self, payload: Any) -> str:
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error") or payload.get("message")
            if detail:
                return self._safe_error_message(Exception(str(detail)))
        if isinstance(payload, str) and payload:
            return self._safe_error_message(Exception(payload[:500]))
        return ""
