from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from secrets import token_urlsafe
from typing import Optional

from ....config import settings
from ....domain.exceptions import NotFoundError, UnauthorizedError, ValidationError
from ....domain.models.entities import CheckoutSession, Order, Payment
from ....domain.models.enums import OrderStatus, PaymentStatus
from ....domain.repositories.interfaces import (
    AddressRepository,
    CheckoutSessionRepository,
    CouponRepository,
    OrderRepository,
    PaymentRepository,
    ProductRepository,
    PromotionRepository,
    UserRepository,
)
from ...dtos.schemas import CreateOrderInput, CreatePaymentPreferenceInput, OrderItemInput
from ..orders.create_order import CreateOrderUseCase
from ..orders.pricing import OrderPricingService
from ..services.points_service import PointsService
from .mercadopago_service import MercadoPagoPayment, MercadoPagoPreference, MercadoPagoService


POINTS_PER_PESO = Decimal("0.01")


class CreatePaymentPreferenceUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        checkout_repo: CheckoutSessionRepository,
        payment_repo: PaymentRepository,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        user_repo: Optional[UserRepository],
        address_repo: Optional[AddressRepository],
        coupon_repo: Optional[CouponRepository],
        delivery_service,
        mp_service: MercadoPagoService,
    ):
        self._orders = order_repo
        self._checkout_sessions = checkout_repo
        self._payments = payment_repo
        self._pricing = OrderPricingService(
            product_repo=product_repo,
            promotion_repo=promotion_repo,
            address_repo=address_repo,
            coupon_repo=coupon_repo,
            user_repo=user_repo,
            delivery_service=delivery_service,
        )
        self._mp = mp_service

    async def execute(
        self,
        data: CreatePaymentPreferenceInput,
        current_user_id: Optional[int] = None,
    ) -> tuple[CheckoutSession, MercadoPagoPreference, Optional[Order]]:
        if data.order_id is not None:
            return await self._execute_legacy_order_preference(data.order_id, current_user_id)

        order_input = self._to_order_input(data)
        pricing = await self._pricing.preview(order_input, user_id=current_user_id)
        checkout_session = await self._checkout_sessions.create(
            CheckoutSession(
                id=None,
                session_token=token_urlsafe(24),
                user_id=current_user_id,
                guest_email=pricing.guest_email if not current_user_id else None,
                guest_phone=pricing.guest_phone if not current_user_id else None,
                address_id=pricing.address_id,
                delivery_type=pricing.delivery_type,
                status="pending",
                payment_provider="mercadopago",
                mp_preference_id=None,
                mp_init_point=None,
                mp_sandbox_init_point=None,
                cart_snapshot=self._cart_snapshot(order_input),
                customer_data=data.customer_data,
                pricing_snapshot=self._pricing_snapshot(pricing),
                delivery_address_snapshot=pricing.delivery_address_snapshot,
                coupon_code=pricing.coupon_code,
                subtotal=pricing.subtotal,
                delivery_fee=pricing.delivery_fee,
                discount=pricing.discount,
                points_used=pricing.points_to_use,
                total=pricing.total,
                created_order_id=None,
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        preference = await self._mp.create_checkout_preference(checkout_session)
        checkout_session = await self._checkout_sessions.update_preference(
            checkout_session.id,
            preference.preference_id,
            preference.init_point,
            preference.sandbox_init_point,
        )
        return checkout_session, preference, None

    async def build_payload(
        self,
        data: CreatePaymentPreferenceInput,
        current_user_id: Optional[int] = None,
    ) -> dict:
        if data.order_id is not None:
            order = await self._orders.get_by_id(data.order_id)
            if not order:
                raise NotFoundError("Pedido", data.order_id)
            self._ensure_payable(order, current_user_id)
            return self._mp.build_preference_payload(order, back_urls=self._legacy_back_urls(order.id))

        order_input = self._to_order_input(data)
        pricing = await self._pricing.preview(order_input, user_id=current_user_id)
        preview_session = CheckoutSession(
            id=0,
            session_token="debug_checkout_session",
            user_id=current_user_id,
            guest_email=pricing.guest_email if not current_user_id else None,
            guest_phone=pricing.guest_phone if not current_user_id else None,
            address_id=pricing.address_id,
            delivery_type=pricing.delivery_type,
            status="pending",
            payment_provider="mercadopago",
            mp_preference_id=None,
            mp_init_point=None,
            mp_sandbox_init_point=None,
            cart_snapshot=self._cart_snapshot(order_input),
            customer_data=data.customer_data,
            pricing_snapshot=self._pricing_snapshot(pricing),
            delivery_address_snapshot=pricing.delivery_address_snapshot,
            coupon_code=pricing.coupon_code,
            subtotal=pricing.subtotal,
            delivery_fee=pricing.delivery_fee,
            discount=pricing.discount,
            points_used=pricing.points_to_use,
            total=pricing.total,
            created_order_id=None,
            expires_at=None,
        )
        return self._mp.build_checkout_preference_payload(preview_session)

    async def _execute_legacy_order_preference(
        self,
        order_id: int,
        current_user_id: Optional[int],
    ) -> tuple[CheckoutSession, MercadoPagoPreference, Optional[Order]]:
        order = await self._orders.get_by_id(order_id)
        if not order:
            raise NotFoundError("Pedido", order_id)
        self._ensure_payable(order, current_user_id)
        preference = await self._mp.create_preference(
            order,
            back_urls=self._legacy_back_urls(order.id),
        )
        order = await self._orders.update_mp_preference(
            order.id,
            preference.preference_id,
            "mercadopago",
            PaymentStatus.PENDING.value,
        )
        legacy_session = CheckoutSession(
            id=None,
            session_token=str(order.id),
            user_id=order.user_id,
            guest_email=order.guest_email,
            guest_phone=order.guest_phone,
            address_id=order.address_id,
            delivery_type=order.delivery_type,
            status="legacy_order",
            payment_provider="mercadopago",
            mp_preference_id=preference.preference_id,
            mp_init_point=preference.init_point,
            mp_sandbox_init_point=preference.sandbox_init_point,
            cart_snapshot={},
            customer_data=None,
            pricing_snapshot=None,
            delivery_address_snapshot=order.delivery_address_snapshot,
            coupon_code=None,
            subtotal=order.subtotal,
            delivery_fee=order.delivery_fee,
            discount=order.discount,
            points_used=order.points_used,
            total=order.total,
            created_order_id=order.id,
            expires_at=None,
        )
        return legacy_session, preference, order

    def _ensure_payable(self, order: Order, current_user_id: Optional[int]) -> None:
        if current_user_id is None and order.user_id is not None:
            raise UnauthorizedError("Debes iniciar sesion para pagar este pedido.")
        if current_user_id is not None and order.user_id not in (None, current_user_id):
            raise UnauthorizedError("No puedes pagar un pedido de otro usuario.")
        if order.payment_status == PaymentStatus.PAID:
            raise ValidationError("El pedido ya se encuentra pagado.")
        if order.total <= 0:
            raise ValidationError("El pedido debe tener un total mayor a 0 para generar pago.")

    def _legacy_back_urls(self, order_id: int) -> dict[str, str]:
        frontend_url = settings.resolved_frontend_public_url
        return {
            "success": f"{frontend_url}/checkout/success?order_id={order_id}",
            "failure": f"{frontend_url}/checkout/failure?order_id={order_id}",
            "pending": f"{frontend_url}/checkout/pending?order_id={order_id}",
        }

    def _to_order_input(self, data: CreatePaymentPreferenceInput) -> CreateOrderInput:
        if data.delivery_type is None:
            raise ValidationError("delivery_type es requerido para crear una preferencia.")
        if not data.items:
            raise ValidationError("items es requerido para crear una preferencia.")
        return CreateOrderInput(
            delivery_type=data.delivery_type,
            address_id=data.address_id,
            guest_email=data.guest_email,
            guest_phone=data.guest_phone,
            items=data.items,
            coupon_code=data.coupon_code,
            points_to_use=data.points_to_use,
            client_totals=data.client_totals,
            notes=data.notes,
        )

    def _cart_snapshot(self, data: CreateOrderInput) -> dict:
        return data.model_dump(mode="json")

    def _pricing_snapshot(self, pricing) -> dict:
        return {
            "items": [
                {
                    "product_id": computed.order_item.product_id,
                    "promotion_id": computed.order_item.promotion_id,
                    "promotion_slot_id": computed.order_item.promotion_slot_id,
                    "product_name": computed.order_item.product_name,
                    "quantity": computed.order_item.quantity,
                    "unit_price": str(computed.order_item.unit_price),
                    "total_price": str(computed.order_item.total_price),
                    "ticket_tag": computed.order_item.ticket_tag.value,
                    "notes": computed.order_item.notes,
                    "selected_modifiers": [
                        {
                            "modifier_option_id": modifier.modifier_option_id,
                            "option_name": modifier.option_name,
                            "group_name": modifier.group_name,
                            "extra_price": str(modifier.extra_price),
                        }
                        for modifier in computed.order_item.modifiers
                    ],
                    "config_json": computed.order_item.config_json,
                }
                for computed in pricing.items
            ],
            "subtotal": str(pricing.subtotal),
            "delivery_fee": str(pricing.delivery_fee),
            "discount": str(pricing.discount),
            "total": str(pricing.total),
            "points_used": pricing.points_to_use,
            "coupon_code": pricing.coupon_code,
            "notes": pricing.notes,
        }


class ProcessMercadoPagoWebhookUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,
        checkout_repo: CheckoutSessionRepository,
        payment_repo: PaymentRepository,
        product_repo: ProductRepository,
        promotion_repo: PromotionRepository,
        user_repo: Optional[UserRepository],
        address_repo: Optional[AddressRepository],
        coupon_repo: Optional[CouponRepository],
        delivery_service,
        mp_service: MercadoPagoService,
    ):
        self._orders = order_repo
        self._checkout_sessions = checkout_repo
        self._payments = payment_repo
        self._product_repo = product_repo
        self._promotion_repo = promotion_repo
        self._user_repo = user_repo
        self._address_repo = address_repo
        self._coupon_repo = coupon_repo
        self._delivery_service = delivery_service
        self._mp = mp_service

    async def execute(self, payment_id: str) -> Order | None:
        mp_payment = await self._mp.get_payment(payment_id)
        checkout_session = await self._resolve_checkout_session(mp_payment)
        if not checkout_session:
            return await self._process_legacy_order_payment(mp_payment)

        mapped_status = self._map_payment_status(mp_payment.status)
        approved_at = datetime.now(UTC) if mapped_status == PaymentStatus.PAID.value else None
        payment = await self._payments.upsert(
            Payment(
                id=None,
                checkout_session_id=checkout_session.id,
                order_id=checkout_session.created_order_id,
                provider="mercadopago",
                provider_payment_id=mp_payment.payment_id,
                provider_preference_id=mp_payment.preference_id or checkout_session.mp_preference_id,
                status=mapped_status,
                provider_status=mp_payment.status,
                amount=mp_payment.amount or checkout_session.total,
                currency="CLP",
                raw_payload=mp_payment.raw,
                approved_at=approved_at,
            )
        )

        if mapped_status != PaymentStatus.PAID.value:
            await self._checkout_sessions.update_status(checkout_session.id, mapped_status)
            return None

        return await self.create_order_from_approved_payment(checkout_session, payment, mp_payment)

    async def create_order_from_approved_payment(
        self,
        checkout_session: CheckoutSession,
        payment: Payment,
        mp_payment: MercadoPagoPayment,
    ) -> Order:
        if payment.order_id:
            existing = await self._orders.get_by_id(payment.order_id)
            if existing:
                return existing

        if checkout_session.created_order_id:
            existing = await self._orders.get_by_id(checkout_session.created_order_id)
            if existing:
                if payment.id:
                    await self._payments.attach_order(payment.id, existing.id)
                return existing

        order_input = CreateOrderInput(**checkout_session.cart_snapshot)
        order = await CreateOrderUseCase(
            order_repo=self._orders,
            product_repo=self._product_repo,
            promotion_repo=self._promotion_repo,
            user_repo=self._user_repo,
            address_repo=self._address_repo,
            coupon_repo=self._coupon_repo,
            delivery_service=self._delivery_service,
            points_service=PointsService(self._user_repo),
        ).execute(order_input, user_id=checkout_session.user_id)

        paid_at = mp_payment.raw.get("date_approved") if isinstance(mp_payment.raw, dict) else None
        paid_at_value = self._parse_datetime(paid_at) or datetime.now(UTC)
        order = await self._orders.update_payment(
            order.id,
            "mercadopago",
            PaymentStatus.PAID.value,
            mp_payment.payment_id,
            mp_payment.status,
            paid_at=paid_at_value,
        )
        if order.can_transition_to(OrderStatus.PAID):
            order = await self._orders.update_status(order.id, OrderStatus.PAID)
        if payment.id:
            await self._payments.attach_order(payment.id, order.id)
        await self._checkout_sessions.update_status(checkout_session.id, PaymentStatus.PAID.value, order.id)
        return order

    async def _resolve_checkout_session(self, payment: MercadoPagoPayment) -> Optional[CheckoutSession]:
        external_reference = payment.external_reference
        if external_reference:
            session = await self._checkout_sessions.get_by_external_reference(str(external_reference))
            if session:
                return session
        metadata = payment.raw.get("metadata") if isinstance(payment.raw, dict) else None
        session_id = metadata.get("checkout_session_id") if isinstance(metadata, dict) else None
        if session_id:
            try:
                return await self._checkout_sessions.get_by_id(int(session_id))
            except (TypeError, ValueError):
                return None
        return None

    async def _process_legacy_order_payment(self, payment: MercadoPagoPayment) -> Order | None:
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

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
