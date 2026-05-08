import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import (
    SQLAddressRepository,
    SQLCheckoutSessionRepository,
    SQLCouponRepository,
    SQLOrderRepository,
    SQLPaymentRepository,
    SQLProductRepository,
    SQLPromotionRepository,
    SQLUserRepository,
)
from ...database.session import get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import (
    CreatePaymentPreferenceInput,
    CreatePaymentPreferenceOut,
    PaymentStatusResponse,
)
from ....application.use_cases.services.delivery_service import DeliveryFeeService
from ....application.use_cases.payments.mercadopago_service import MercadoPagoService
from ....application.use_cases.payments.payment_use_cases import (
    CreatePaymentPreferenceUseCase,
    ProcessMercadoPagoWebhookUseCase,
)
from ....auth import get_optional_user
from ....config import settings
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


router = APIRouter(prefix="/payments", tags=["Pagos"])
logger = logging.getLogger(__name__)


@router.post("/create-preference", response_model=CreatePaymentPreferenceOut)
async def create_payment_preference(
    data: CreatePaymentPreferenceInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    try:
        checkout_session, preference, order = await CreatePaymentPreferenceUseCase(
            order_repo=SQLOrderRepository(db),
            checkout_repo=SQLCheckoutSessionRepository(db),
            payment_repo=SQLPaymentRepository(db),
            product_repo=SQLProductRepository(db),
            promotion_repo=SQLPromotionRepository(db),
            user_repo=SQLUserRepository(db),
            address_repo=SQLAddressRepository(db),
            coupon_repo=SQLCouponRepository(db),
            delivery_service=DeliveryFeeService(),
            mp_service=MercadoPagoService(),
        ).execute(
            data=data,
            current_user_id=current_user.id if current_user else None,
        )
        return CreatePaymentPreferenceOut(
            preference_id=preference.preference_id,
            init_point=preference.init_point,
            sandbox_init_point=preference.sandbox_init_point,
            checkout_session_id=checkout_session.id,
            external_reference=checkout_session.external_reference,
            order_id=order.id if order else None,
        )
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.post("/debug/preference-payload")
async def debug_payment_preference_payload(
    data: CreatePaymentPreferenceInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        payload = await CreatePaymentPreferenceUseCase(
            order_repo=SQLOrderRepository(db),
            checkout_repo=SQLCheckoutSessionRepository(db),
            payment_repo=SQLPaymentRepository(db),
            product_repo=SQLProductRepository(db),
            promotion_repo=SQLPromotionRepository(db),
            user_repo=SQLUserRepository(db),
            address_repo=SQLAddressRepository(db),
            coupon_repo=SQLCouponRepository(db),
            delivery_service=DeliveryFeeService(),
            mp_service=MercadoPagoService(),
        ).build_payload(
            data=data,
            current_user_id=current_user.id if current_user else None,
        )
        return JSONResponse(payload)
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.get("/debug/mp-token")
async def debug_mercadopago_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _ensure_internal_debug_allowed(x_internal_token)
    token = settings.mp_access_token
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(base_url="https://api.mercadopago.com", timeout=15.0) as client:
            response = await client.get("/users/me", headers=headers)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "status_code": None,
                "response": {"error": str(exc)},
                "token_prefix": _token_prefix(token),
                "token_type": _token_type(token),
            },
        )

    return {
        "status_code": response.status_code,
        "response": _parse_response_body(response),
        "token_prefix": _token_prefix(token),
        "token_type": _token_type(token),
    }


@router.get("/status/{external_reference}", response_model=PaymentStatusResponse)
async def get_payment_status(
    external_reference: str,
    db: AsyncSession = Depends(get_db),
):
    checkout_repo = SQLCheckoutSessionRepository(db)
    payment_repo = SQLPaymentRepository(db)
    order_repo = SQLOrderRepository(db)

    checkout_session = await checkout_repo.get_by_external_reference(external_reference)
    if not checkout_session:
        raise HTTPException(status_code=404, detail="Checkout no encontrado.")

    payments = await payment_repo.get_by_checkout_session_id(checkout_session.id)
    latest_payment = max(payments, key=lambda payment: payment.updated_at or payment.created_at) if payments else None

    order = None
    if checkout_session.created_order_id:
        order = await order_repo.get_by_id(checkout_session.created_order_id)
    elif latest_payment and latest_payment.order_id:
        order = await order_repo.get_by_id(latest_payment.order_id)

    checkout_status = _public_checkout_status(checkout_session.status, bool(order))
    payment_status = _public_payment_status(
        latest_payment.status if latest_payment else None,
        latest_payment.provider_status if latest_payment else None,
    )
    order_status = _public_order_status(order.status.value if order else None)

    return PaymentStatusResponse(
        external_reference=external_reference,
        checkout_session_status=checkout_status,
        payment_status=payment_status,
        order_id=order.id if order else None,
        order_status=order_status,
        total=checkout_session.total,
        created_at=checkout_session.created_at,
        updated_at=checkout_session.updated_at,
        message=_payment_status_message(checkout_status, payment_status, bool(order)),
    )


@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await process_mercadopago_webhook_request(request, x_signature, db)


async def process_mercadopago_webhook_request(
    request: Request,
    x_signature: Optional[str],
    db: AsyncSession,
    *,
    deprecated_route: bool = False,
):
    service = MercadoPagoService()
    body = await request.body()
    if settings.mp_webhook_secret:
        if not x_signature:
            logger.warning(
                "Mercado Pago webhook rejected: missing signature",
                extra={"deprecated_route": deprecated_route},
            )
            return JSONResponse({"detail": "Firma de webhook requerida"}, status_code=401)
        if not _verify_signature(service, body, x_signature):
            logger.warning(
                "Mercado Pago webhook rejected: invalid signature",
                extra={"deprecated_route": deprecated_route},
            )
            return JSONResponse({"detail": "Firma de webhook invalida"}, status_code=401)

    try:
        payload = json.loads(body.decode() or "{}")
    except ValueError:
        return JSONResponse({"detail": "Payload invalido"}, status_code=400)

    event_type = payload.get("type") or payload.get("topic") or request.query_params.get("type")
    if event_type != "payment":
        return JSONResponse({"status": "ignored"})

    payment_id = _extract_payment_id(payload, request)
    if not payment_id:
        return JSONResponse({"status": "ignored"})

    try:
        order = await ProcessMercadoPagoWebhookUseCase(
            order_repo=SQLOrderRepository(db),
            checkout_repo=SQLCheckoutSessionRepository(db),
            payment_repo=SQLPaymentRepository(db),
            product_repo=SQLProductRepository(db),
            promotion_repo=SQLPromotionRepository(db),
            user_repo=SQLUserRepository(db),
            address_repo=SQLAddressRepository(db),
            coupon_repo=SQLCouponRepository(db),
            delivery_service=DeliveryFeeService(),
            mp_service=service,
        ).execute(payment_id)
    except DomainError:
        return JSONResponse({"status": "ignored"})

    logger.info(
        "Mercado Pago webhook handled",
        extra={
            "provider_payment_id": payment_id,
            "order_id": order.id if order else None,
            "result": "processed",
            "deprecated_route": deprecated_route,
        },
    )
    return JSONResponse({"status": "processed"})


def _extract_payment_id(payload: dict, request: Request) -> Optional[str]:
    candidates = [
        payload.get("data", {}).get("id"),
        payload.get("resource", "").rstrip("/").split("/")[-1] if payload.get("resource") else None,
        payload.get("id"),
        request.query_params.get("data.id"),
        request.query_params.get("id"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _public_checkout_status(status: str, has_order: bool) -> str:
    if has_order:
        return "paid"
    normalized = (status or "").lower()
    mapping = {
        "pagado": "paid",
        "paid": "paid",
        "pendiente": "pending",
        "pending": "pending",
        "processing_order": "pending",
        "rechazado": "failed",
        "rejected": "failed",
        "failed": "failed",
        "expired": "expired",
        "amount_mismatch": "amount_mismatch",
    }
    return mapping.get(normalized, "pending")


def _public_payment_status(status: Optional[str], provider_status: Optional[str]) -> Optional[str]:
    if status == "amount_mismatch":
        return "amount_mismatch"
    normalized = (provider_status or status or "").lower()
    if not normalized:
        return None
    if normalized in {"approved", "pagado", "paid"}:
        return "approved"
    if normalized in {"rejected", "cancelled", "cancelled_by_user", "refunded", "charged_back", "rechazado"}:
        return "rejected"
    if normalized in {"pending", "in_process", "authorized", "pendiente"}:
        return "pending"
    return "pending"


def _public_order_status(status: Optional[str]) -> Optional[str]:
    mapping = {
        "pendiente": "pending",
        "pagado": "confirmed",
        "en_preparacion": "preparing",
        "listo": "ready",
        "despachado": "dispatched",
        "entregado": "delivered",
        "cancelado": "cancelled",
        "anulado": "voided",
    }
    return mapping.get(status) if status else None


def _payment_status_message(
    checkout_status: str,
    payment_status: Optional[str],
    has_order: bool,
) -> str:
    if checkout_status == "amount_mismatch":
        return "Detectamos una diferencia en el monto aprobado. Contacta a Yakero para revisar tu pago."
    if payment_status == "rejected" or checkout_status == "failed":
        return "El pago fue rechazado. Puedes volver al checkout e intentarlo nuevamente."
    if has_order:
        return "Pago aprobado. Tu pedido fue creado y ya esta en preparacion operativa."
    if payment_status == "approved":
        return "Pago aprobado. Estamos terminando de crear tu pedido."
    return "Estamos esperando la confirmacion de Mercado Pago."


def _ensure_internal_debug_allowed(x_internal_token: str | None) -> None:
    if not settings.internal_bootstrap_token:
        raise HTTPException(status_code=503, detail="INTERNAL_BOOTSTRAP_TOKEN no configurado.")
    if not x_internal_token or x_internal_token != settings.internal_bootstrap_token:
        raise HTTPException(status_code=401, detail="Token interno invalido.")


def _token_prefix(token: str) -> str:
    return token[:8] if token else ""


def _token_type(token: str) -> str:
    if token.startswith("TEST-"):
        return "TEST"
    if token.startswith("APP_USR-"):
        return "APP_USR"
    return "UNKNOWN"


def _parse_response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _verify_signature(service: MercadoPagoService, body: bytes, signature: str) -> bool:
    # El SDK anterior verificaba HMAC simple. Conservamos compatibilidad local sin
    # bloquear cuando no hay secret configurado.
    from ....infrastructure.payment.mercadopago_service import MercadoPagoService as LegacyMercadoPagoService

    return LegacyMercadoPagoService().verify_webhook_signature(body.decode(), signature)
