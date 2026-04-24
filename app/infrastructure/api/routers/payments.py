from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import (
    CreatePaymentPreferenceInput,
    CreatePaymentPreferenceOut,
)
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


@router.post("/create-preference", response_model=CreatePaymentPreferenceOut)
async def create_payment_preference(
    data: CreatePaymentPreferenceInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    try:
        order, preference = await CreatePaymentPreferenceUseCase(
            order_repo=SQLOrderRepository(db),
            mp_service=MercadoPagoService(),
        ).execute(
            order_id=data.order_id,
            current_user_id=current_user.id if current_user else None,
        )
        return CreatePaymentPreferenceOut(
            preference_id=preference.preference_id,
            init_point=preference.init_point,
            sandbox_init_point=preference.sandbox_init_point,
            order_id=order.id,
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
            mp_service=MercadoPagoService(),
        ).build_payload(
            order_id=data.order_id,
            current_user_id=current_user.id if current_user else None,
        )
        return JSONResponse(payload)
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = MercadoPagoService()
    if x_signature:
        from ....config import settings

        if settings.mp_webhook_secret and not _verify_signature(service, await request.body(), x_signature):
            return JSONResponse({"status": "invalid signature"}, status_code=401)

    payload = await request.json()
    event_type = payload.get("type") or payload.get("topic") or request.query_params.get("type")
    if event_type != "payment":
        return JSONResponse({"status": "ignored"})

    payment_id = _extract_payment_id(payload, request)
    if not payment_id:
        return JSONResponse({"status": "ignored"})

    try:
        await ProcessMercadoPagoWebhookUseCase(
            order_repo=SQLOrderRepository(db),
            mp_service=service,
        ).execute(payment_id)
    except DomainError:
        return JSONResponse({"status": "ignored"})

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


def _verify_signature(service: MercadoPagoService, body: bytes, signature: str) -> bool:
    # El SDK anterior verificaba HMAC simple. Conservamos compatibilidad local sin
    # bloquear cuando no hay secret configurado.
    from ....infrastructure.payment.mercadopago_service import MercadoPagoService as LegacyMercadoPagoService

    return LegacyMercadoPagoService().verify_webhook_signature(body.decode(), signature)
