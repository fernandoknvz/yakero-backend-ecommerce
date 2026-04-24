from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from ....config import settings
from ....domain.exceptions import NotFoundError, PaymentError, UnauthorizedError, ValidationError
from ....domain.models.entities import Order
from ....domain.models.enums import OrderStatus, PaymentStatus
from ....domain.repositories.interfaces import OrderRepository
from .mercadopago_service import MercadoPagoPreference, MercadoPagoService


class CreatePaymentPreferenceUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        mp_service: MercadoPagoService,
    ):
        self._orders = order_repo
        self._mp = mp_service

    async def execute(
        self,
        order_id: int,
        current_user_id: Optional[int] = None,
    ) -> tuple[Order, MercadoPagoPreference]:
        order = await self._orders.get_by_id(order_id)
        if not order:
            raise NotFoundError("Pedido", order_id)
        self._ensure_payable(order, current_user_id)

        preference = await self._mp.create_preference(
            order,
            back_urls={
                "success": f"{settings.app_base_url}/checkout/success?order_id={order.id}",
                "failure": f"{settings.app_base_url}/checkout/failure?order_id={order.id}",
                "pending": f"{settings.app_base_url}/checkout/pending?order_id={order.id}",
            },
        )
        updated = await self._orders.update_mp_preference(
            order.id,
            preference.preference_id,
            "mercadopago",
            PaymentStatus.PENDING.value,
        )
        return updated, preference

    def _ensure_payable(self, order: Order, current_user_id: Optional[int]) -> None:
        if current_user_id is None and order.user_id is not None:
            raise UnauthorizedError("Debes iniciar sesion para pagar este pedido.")
        if current_user_id is not None and order.user_id not in (None, current_user_id):
            raise UnauthorizedError("No puedes pagar un pedido de otro usuario.")
        if order.payment_status == PaymentStatus.PAID:
            raise ValidationError("El pedido ya se encuentra pagado.")
        if order.total <= 0:
            raise ValidationError("El pedido debe tener un total mayor a 0 para generar pago.")

    async def build_payload(
        self,
        order_id: int,
        current_user_id: Optional[int] = None,
    ) -> dict:
        order = await self._orders.get_by_id(order_id)
        if not order:
            raise NotFoundError("Pedido", order_id)
        self._ensure_payable(order, current_user_id)
        return self._mp.build_preference_payload(
            order,
            back_urls={
                "success": f"{settings.app_base_url}/checkout/success?order_id={order.id}",
                "failure": f"{settings.app_base_url}/checkout/failure?order_id={order.id}",
                "pending": f"{settings.app_base_url}/checkout/pending?order_id={order.id}",
            },
        )


class ProcessMercadoPagoWebhookUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        mp_service: MercadoPagoService,
    ):
        self._orders = order_repo
        self._mp = mp_service

    async def execute(self, payment_id: str) -> Order | None:
        payment = await self._mp.get_payment(payment_id)
        order_id = self._extract_order_id(payment.external_reference)
        if order_id is None:
            return None

        order = await self._orders.get_by_id(order_id)
        if not order:
            return None

        mapped_status = self._map_payment_status(payment.status)
        paid_at = datetime.now(UTC) if mapped_status == PaymentStatus.PAID.value else order.paid_at

        updated = await self._orders.update_payment(
            order.id,
            "mercadopago",
            mapped_status,
            payment.payment_id,
            payment.status,
            paid_at=paid_at,
        )

        if mapped_status == PaymentStatus.PAID.value and updated.can_transition_to(OrderStatus.PAID):
            updated = await self._orders.update_status(updated.id, OrderStatus.PAID)
        return updated

    def _extract_order_id(self, external_reference: Optional[str]) -> Optional[int]:
        if not external_reference:
            return None
        try:
            return int(external_reference)
        except (TypeError, ValueError):
            return None

    def _map_payment_status(self, mp_status: str) -> str:
        normalized = (mp_status or "").lower()
        if normalized == "approved":
            return PaymentStatus.PAID.value
        if normalized in {"pending", "in_process", "authorized"}:
            return PaymentStatus.PENDING.value
        if normalized in {"rejected", "cancelled", "cancelled_by_user", "refunded", "charged_back"}:
            return PaymentStatus.REJECTED.value
        return PaymentStatus.PENDING.value
