from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from ....config import settings
from ....domain.models.entities import CheckoutSession, Order, OrderItem, Payment
from ....domain.models.enums import DeliveryType
from ....domain.repositories.interfaces import OrderRepository, ProductRepository, PromotionRepository
from ....infrastructure.clients import PosClient, PosClientError


logger = logging.getLogger(__name__)


class PosOrderSyncService:
    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        pos_client: Optional[PosClient] = None,
    ):
        self._orders = order_repo
        self._products = product_repo
        self._promotions = promotion_repo
        self._pos = pos_client or PosClient()

    async def sync_paid_order(
        self,
        *,
        order: Order,
        checkout_session: Optional[CheckoutSession],
        payment: Optional[Payment],
        total_paid: Decimal,
    ) -> Order:
        if not order.id:
            return order
        if order.pos_sale_id:
            logger.info(
                "POS order sync skipped because order already has pos_sale_id",
                extra={"order_id": order.id, "pos_sync_status": order.pos_sync_status},
            )
            return order

        payload = await self.build_payload(
            order=order,
            checkout_session=checkout_session,
            payment=payment,
            total_paid=total_paid,
        )

        try:
            response = await self._pos.send_order_to_pos(payload)
        except PosClientError as exc:
            logger.warning(
                "POS order sync failed order_id=%s status_code=%s provider_status_code=%s message=%s",
                order.id,
                exc.status_code,
                exc.provider_status_code,
                exc.message,
            )
            return await self._orders.mark_pos_sync_failed(order.id, exc.message)

        sanitized = self._sanitize_response(response)
        if self._is_accepted(response):
            return await self._orders.mark_pos_sync_success(
                order.id,
                self._extract_pos_sale_id(response),
                sanitized,
            )

        error = self._extract_error(response) or "POS did not accept ecommerce order."
        return await self._orders.mark_pos_sync_failed(order.id, error, sanitized)

    async def build_payload(
        self,
        *,
        order: Order,
        checkout_session: Optional[CheckoutSession],
        payment: Optional[Payment],
        total_paid: Decimal,
    ) -> dict[str, Any]:
        customer_data = checkout_session.customer_data if checkout_session else None
        delivery = order.delivery_address_snapshot or {}
        external_order_id = self.external_order_id(order, checkout_session)
        return {
            "external_order_id": external_order_id,
            "external_payment_id": payment.provider_payment_id if payment else order.mp_payment_id,
            "payment_provider": "mercadopago",
            "payment_status": "approved",
            "branch_external_code": self._branch_external_code(customer_data),
            "fulfillment_type": self._fulfillment_type(order),
            "customer": self._customer(order, checkout_session),
            "delivery": {
                "address": self._delivery_address(delivery),
                "commune": self._first_string(delivery, "commune", "comuna"),
                "reference": self._first_string(delivery, "notes", "reference", "referencia"),
                "fee": self._number(order.delivery_fee),
                "lat": self._first_number(delivery, "latitude", "lat"),
                "lng": self._first_number(delivery, "longitude", "lng", "lon"),
            },
            "items": [await self._item_payload(item) for item in order.items],
            "totals": {
                "subtotal": self._number(order.subtotal),
                "delivery_fee": self._number(order.delivery_fee),
                "discount": self._number(order.discount),
                "total_paid": self._number(total_paid),
            },
            "dry_run": settings.pos_ecommerce_dry_run,
        }

    def external_order_id(self, order: Order, checkout_session: Optional[CheckoutSession]) -> str:
        if checkout_session:
            return checkout_session.external_reference
        return str(order.id)

    async def _item_payload(self, item: OrderItem) -> dict[str, Any]:
        item_type = "promotion" if item.promotion_id else "product"
        external_code = await self._external_item_code(item)
        return {
            "type": item_type,
            "external_code": external_code,
            "quantity": item.quantity,
            "notes": item.notes or "",
            "options": [
                {
                    "name": modifier.option_name,
                    "group_name": modifier.group_name,
                    "extra_price": self._number(modifier.extra_price),
                }
                for modifier in item.modifiers
            ],
            "rellenos": self._rellenos(item.config_json),
        }

    async def _external_item_code(self, item: OrderItem) -> str:
        if item.promotion_id:
            promotion = await self._promotions.get_by_id(item.promotion_id)
            return (promotion.external_code if promotion else None) or str(item.promotion_id)
        if item.product_id:
            product = await self._products.get_by_id(item.product_id)
            return (product.sku if product else None) or str(item.product_id)
        return ""

    def _customer(self, order: Order, checkout_session: Optional[CheckoutSession]) -> dict[str, str]:
        data = checkout_session.customer_data if checkout_session else None
        return {
            "name": self._first_string(data, "name", "full_name", "nombre") or "",
            "phone": self._first_string(data, "phone", "telefono") or order.guest_phone or "",
            "email": self._first_string(data, "email", "correo") or order.guest_email or "",
        }

    def _branch_external_code(self, customer_data: Optional[dict[str, Any]]) -> str:
        direct = self._first_string(customer_data, "branch_external_code", "branch_code", "sucursal")
        if direct:
            return direct
        branch = customer_data.get("branch") if isinstance(customer_data, dict) else None
        return self._first_string(branch, "external_code", "code", "id") or ""

    def _fulfillment_type(self, order: Order) -> str:
        return "delivery" if order.delivery_type == DeliveryType.DELIVERY else "pickup"

    def _delivery_address(self, delivery: dict[str, Any]) -> str:
        street = self._first_string(delivery, "street", "calle")
        number = self._first_string(delivery, "number", "numero")
        return " ".join(part for part in [street, number] if part).strip()

    def _rellenos(self, config_json: Optional[dict[str, Any]]) -> list[Any]:
        if not isinstance(config_json, dict):
            return []
        rellenos = config_json.get("rellenos")
        return rellenos if isinstance(rellenos, list) else []

    def _is_accepted(self, response: dict[str, Any]) -> bool:
        return bool(response.get("accepted")) or bool(response.get("duplicate"))

    def _extract_pos_sale_id(self, response: dict[str, Any]) -> Optional[str]:
        value = response.get("pos_sale_id") or response.get("sale_id") or response.get("id")
        return str(value) if value is not None else None

    def _extract_error(self, response: dict[str, Any]) -> str:
        value = response.get("error") or response.get("detail") or response.get("message")
        return str(value) if value else ""

    def _sanitize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        blocked = {"token", "internal_token", "x_internal_token", "authorization"}
        return {key: value for key, value in response.items() if key.lower() not in blocked}

    def _number(self, value: Decimal | int | float | None) -> int | float:
        if value is None:
            return 0
        decimal = Decimal(value)
        if decimal == decimal.to_integral_value():
            return int(decimal)
        return float(decimal)

    def _first_string(self, data: Optional[dict[str, Any]], *keys: str) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _first_number(self, data: Optional[dict[str, Any]], *keys: str) -> float | None:
        value = self._first_string(data, *keys)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None
