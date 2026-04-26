from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from ....config import settings
from ....domain.exceptions import PaymentError
from ....domain.models.entities import CheckoutSession, Order


logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class MercadoPagoPreference:
    preference_id: str
    init_point: Optional[str]
    sandbox_init_point: Optional[str]


@dataclass
class MercadoPagoPayment:
    payment_id: str
    status: str
    external_reference: Optional[str]
    preference_id: Optional[str]
    amount: Optional[Decimal]
    raw: dict[str, Any]


class MercadoPagoService:
    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: str = "https://api.mercadopago.com",
        timeout: float = 15.0,
    ):
        self._access_token = access_token or settings.mp_access_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def create_preference(self, order: Order, back_urls: dict[str, str]) -> MercadoPagoPreference:
        self._ensure_configured()
        payload = self.build_preference_payload(order, back_urls)
        if settings.debug:
            logger.info("Mercado Pago preference payload prepared: %s", self._safe_json(payload))
        response = await self._request("POST", "/checkout/preferences", json=payload)
        preference_id = response.get("id")
        if not preference_id:
            raise PaymentError(
                "Mercado Pago no devolvio un preference_id valido.",
                debug_detail={"response": response},
            )
        return MercadoPagoPreference(
            preference_id=str(preference_id),
            init_point=response.get("init_point"),
            sandbox_init_point=response.get("sandbox_init_point"),
        )

    async def create_checkout_preference(
        self,
        checkout_session: CheckoutSession,
    ) -> MercadoPagoPreference:
        self._ensure_configured()
        payload = self.build_checkout_preference_payload(checkout_session)
        if settings.debug:
            logger.info("Mercado Pago checkout preference payload prepared: %s", self._safe_json(payload))
        response = await self._request("POST", "/checkout/preferences", json=payload)
        preference_id = response.get("id")
        if not preference_id:
            raise PaymentError(
                "Mercado Pago no devolvio un preference_id valido.",
                debug_detail={"response": response},
            )
        return MercadoPagoPreference(
            preference_id=str(preference_id),
            init_point=response.get("init_point"),
            sandbox_init_point=response.get("sandbox_init_point"),
        )

    async def get_payment(self, payment_id: str) -> MercadoPagoPayment:
        self._ensure_configured()
        response = await self._request("GET", f"/v1/payments/{payment_id}")
        return MercadoPagoPayment(
            payment_id=str(response.get("id") or payment_id),
            status=str(response.get("status") or ""),
            external_reference=response.get("external_reference"),
            preference_id=response.get("order", {}).get("id") or response.get("preference_id"),
            amount=Decimal(str(response.get("transaction_amount"))) if response.get("transaction_amount") is not None else None,
            raw=response,
        )

    def build_preference_payload(self, order: Order, back_urls: dict[str, str]) -> dict[str, Any]:
        notification_url = f"{settings.api_base_url}{settings.api_v1_prefix}/payments/webhook"
        payload = {
            "items": self._build_items(order),
            "external_reference": str(order.id),
            "notification_url": notification_url,
            "back_urls": {key: str(value) for key, value in back_urls.items()},
            "auto_return": "approved",
            "metadata": {
                "order_id": order.id,
                "environment": settings.mp_env,
            },
        }
        payer_email = self._resolve_payer_email(order)
        if payer_email:
            payload["payer"] = {"email": payer_email}
        self._validate_payload(payload)
        return payload

    def build_checkout_preference_payload(self, checkout_session: CheckoutSession) -> dict[str, Any]:
        backend_url = settings.resolved_backend_public_url
        frontend_url = settings.resolved_frontend_public_url
        payload = {
            "items": self._build_checkout_items(checkout_session),
            "external_reference": checkout_session.external_reference,
            "notification_url": f"{backend_url}{settings.api_v1_prefix}/payments/webhook",
            "back_urls": {
                "success": f"{frontend_url}/checkout/success?checkout_session_id={checkout_session.id}",
                "failure": f"{frontend_url}/checkout/failure?checkout_session_id={checkout_session.id}",
                "pending": f"{frontend_url}/checkout/pending?checkout_session_id={checkout_session.id}",
            },
            "auto_return": "approved",
            "metadata": {
                "checkout_session_id": checkout_session.id,
                "environment": settings.mp_env,
            },
        }
        payer_email = checkout_session.guest_email
        if self._is_valid_email(payer_email):
            payload["payer"] = {"email": payer_email.strip()}
        self._validate_payload(payload)
        return payload

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        headers["Content-Type"] = "application/json"
        payload = kwargs.get("json")
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            try:
                response = await client.request(method, path, headers=headers, **kwargs)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                response_text = exc.response.text
                response_json = self._parse_json_safely(response_text)
                safe_payload = self._safe_payload(payload)
                logger.warning(
                    "Mercado Pago API error status=%s payload=%s response=%s",
                    exc.response.status_code,
                    self._safe_json(safe_payload),
                    self._safe_json(response_json if response_json is not None else response_text),
                )
                public_message = "Error al crear preferencia de pago en Mercado Pago."
                if exc.response.status_code in {400, 401, 403}:
                    public_message = (
                        "Mercado Pago rechazo la solicitud. Revisa configuracion, credenciales TEST y URLs publicas."
                    )
                raise PaymentError(
                    public_message,
                    status_code=exc.response.status_code if exc.response.status_code in {400, 401, 403} else 502,
                    debug_detail={
                        "provider": "mercadopago",
                        "provider_status_code": exc.response.status_code,
                        "provider_response": response_json if response_json is not None else response_text,
                        "request_payload": safe_payload,
                    },
                ) from exc
            except httpx.HTTPError as exc:
                logger.exception(
                    "Mercado Pago communication error payload=%s",
                    self._safe_json(self._safe_payload(payload)),
                )
                raise PaymentError(
                    f"Error de comunicacion con Mercado Pago: {exc}",
                    status_code=502,
                    debug_detail={
                        "provider": "mercadopago",
                        "request_payload": self._safe_payload(payload),
                    },
                ) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise PaymentError(
                "Mercado Pago respondio con un payload invalido.",
                debug_detail={"raw_response": response.text},
            ) from exc

    def _build_items(self, order: Order) -> list[dict[str, Any]]:
        items = [
            {
                "id": str(item.product_id or item.promotion_id or item.id or "item"),
                "title": str(item.product_name),
                "quantity": int(item.quantity),
                "unit_price": float(item.unit_price),
                "currency_id": "CLP",
            }
            for item in order.items
        ]
        if order.delivery_fee > 0:
            items.append(
                {
                    "id": "delivery",
                    "title": "Costo de envio",
                    "quantity": 1,
                    "unit_price": float(order.delivery_fee),
                    "currency_id": "CLP",
                }
            )
        return items

    def _build_checkout_items(self, checkout_session: CheckoutSession) -> list[dict[str, Any]]:
        pricing = checkout_session.pricing_snapshot or {}
        items = [
            {
                "id": str(item.get("product_id") or item.get("promotion_id") or "item"),
                "title": str(item["product_name"]),
                "quantity": int(item["quantity"]),
                "unit_price": float(Decimal(str(item["unit_price"]))),
                "currency_id": "CLP",
            }
            for item in pricing.get("items", [])
        ]
        if checkout_session.delivery_fee > 0:
            items.append(
                {
                    "id": "delivery",
                    "title": "Costo de envio",
                    "quantity": 1,
                    "unit_price": float(checkout_session.delivery_fee),
                    "currency_id": "CLP",
                }
            )
        return items

    def _ensure_configured(self) -> None:
        if not self._access_token:
            raise PaymentError("MP_ACCESS_TOKEN no configurado.", status_code=500)
        if settings.mp_env not in {"sandbox", "production"}:
            raise PaymentError(
                "MP_ENV debe ser sandbox o production.",
                status_code=500,
                debug_detail={"mp_env": settings.mp_env},
            )
        if settings.mp_env == "production" and self._access_token.startswith("TEST-"):
            raise PaymentError("MP_ACCESS_TOKEN TEST no permitido en production.", status_code=500)

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        notification_url = payload["notification_url"]
        if not self._is_absolute_url(notification_url):
            raise PaymentError(
                "notification_url debe ser absoluta.",
                status_code=500,
                debug_detail={"notification_url": notification_url},
            )
        if self._is_local_url(notification_url):
            raise PaymentError(
                "API_BASE_URL no puede apuntar a localhost o 127.0.0.1 para webhooks de Mercado Pago. Usa ngrok HTTPS.",
                status_code=500,
                debug_detail={"notification_url": notification_url},
            )
        if urlparse(notification_url).scheme != "https":
            raise PaymentError(
                "notification_url debe usar HTTPS.",
                status_code=500,
                debug_detail={"notification_url": notification_url},
            )
        for key, url in payload["back_urls"].items():
            if not self._is_absolute_url(url):
                raise PaymentError(
                    f"back_urls.{key} debe ser absoluta.",
                    status_code=500,
                    debug_detail={"back_url": url},
                )
        if payload["auto_return"] != "approved":
            raise PaymentError("auto_return invalido.", status_code=500)
        if not isinstance(payload["external_reference"], str):
            raise PaymentError("external_reference debe ser string.", status_code=500)
        payer = payload.get("payer")
        if payer is not None:
            email = payer.get("email")
            if not isinstance(email, str) or not self._is_valid_email(email):
                raise PaymentError(
                    "payer.email debe tener formato valido.",
                    status_code=500,
                    debug_detail={"payer": payer},
                )
        for item in payload["items"]:
            if not isinstance(item["title"], str) or not item["title"].strip():
                raise PaymentError(
                    "Cada item debe tener title valido.",
                    status_code=500,
                    debug_detail={"item": item},
                )
            if not isinstance(item["quantity"], int):
                raise PaymentError(
                    "Cada item debe tener quantity int.",
                    status_code=500,
                    debug_detail={"item": item},
                )
            if not isinstance(item["unit_price"], (int, float)):
                raise PaymentError(
                    "Cada item debe tener unit_price numerico.",
                    status_code=500,
                    debug_detail={"item": item},
                )
            if item["currency_id"] != "CLP":
                raise PaymentError(
                    "currency_id debe ser CLP.",
                    status_code=500,
                    debug_detail={"item": item},
                )

    def _is_absolute_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return bool(parsed.scheme and parsed.netloc)

    def _is_local_url(self, value: str) -> bool:
        hostname = (urlparse(value).hostname or "").lower()
        return hostname in {"localhost", "127.0.0.1", "0.0.0.0"}

    def _safe_payload(self, payload: Any) -> Any:
        if payload is None:
            return None
        return json.loads(json.dumps(payload, default=self._json_default))

    def _safe_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=self._json_default)

    def _json_default(self, value: Any):
        if isinstance(value, Decimal):
            return float(value)
        return str(value)

    def _parse_json_safely(self, response_text: str) -> Any:
        try:
            return json.loads(response_text)
        except ValueError:
            return None

    def _resolve_payer_email(self, order: Order) -> Optional[str]:
        if self._is_valid_email(order.guest_email):
            return order.guest_email.strip()
        return None

    def _is_valid_email(self, value: Optional[str]) -> bool:
        if not value or not isinstance(value, str):
            return False
        return bool(EMAIL_RE.match(value.strip()))
