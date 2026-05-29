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
        self._base_url = (base_url if base_url is not None else settings.pos_api_base_url).rstrip("/")
        self._internal_token = internal_token if internal_token is not None else settings.pos_internal_token
        self._timeout = timeout if timeout is not None else settings.pos_catalog_timeout_seconds
        self._transport = transport

    async def get_catalog_summary(self) -> dict[str, Any]:
        return await self._get("/api/external/catalog/summary")

    async def get_products(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/products")

    async def get_promotions(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/promotions")

    async def get_branches(self) -> dict[str, Any] | list[Any]:
        return await self._get("/api/external/catalog/branches")

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get(self, path: str) -> Any:
        self._ensure_configured()
        headers = {"X-Internal-Token": self._internal_token}

        logger.info(
            "POS catalog request started url=%s header_names=%s token_configured=%s",
            self._full_url(path),
            list(headers.keys()),
            bool(self._internal_token),
        )
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            try:
                response = await client.get(path, headers=headers)
                logger.info(
                    "POS catalog response endpoint=%s status_code=%s",
                    path,
                    response.status_code,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "POS catalog HTTP error endpoint=%s status_code=%s message=%s",
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
                if status_code >= 500:
                    raise PosClientError(
                        "POS unavailable or returned an upstream error.",
                        status_code=502,
                        provider_status_code=status_code,
                    ) from exc
                raise PosClientError(
                    "POS catalog request was rejected.",
                    status_code=502,
                    provider_status_code=status_code,
                ) from exc
            except httpx.TimeoutException as exc:
                logger.warning(
                    "POS catalog timeout endpoint=%s exception_type=%s message=%s",
                    path,
                    type(exc).__name__,
                    self._safe_error_message(exc),
                )
                raise PosClientError("POS catalog request timed out.", status_code=502) from exc
            except httpx.HTTPError as exc:
                logger.warning(
                    "POS catalog network error endpoint=%s exception_type=%s message=%s",
                    path,
                    type(exc).__name__,
                    self._safe_error_message(exc),
                )
                raise PosClientError("POS unavailable or network error.", status_code=502) from exc

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("POS catalog invalid JSON endpoint=%s", path)
            raise PosClientError("POS returned an invalid JSON response.", status_code=502) from exc

    def _ensure_configured(self) -> None:
        if not self._base_url:
            raise PosClientError("POS_API_BASE_URL is not configured.", status_code=500)
        if not self._internal_token:
            raise PosClientError("POS_INTERNAL_TOKEN is not configured.", status_code=500)
        if self._timeout <= 0:
            raise PosClientError("POS_CATALOG_TIMEOUT_SECONDS must be greater than 0.", status_code=500)

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if self._internal_token:
            message = message.replace(self._internal_token, "***")
        return message

    def _full_url(self, path: str) -> str:
        return f"{self._base_url}{path}"
