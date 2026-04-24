from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import get_db
from ....application.use_cases.payments.mercadopago_service import MercadoPagoService
from ....application.use_cases.payments.payment_use_cases import ProcessMercadoPagoWebhookUseCase
from ....config import settings
from ....domain.exceptions import DomainError
from ...payment.mercadopago_service import MercadoPagoService as LegacyMercadoPagoService


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/mercadopago")
async def mp_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    if x_signature and settings.mp_webhook_secret:
        if not LegacyMercadoPagoService().verify_webhook_signature(body.decode(), x_signature):
            return JSONResponse({"detail": "Firma de webhook invalida"}, status_code=401)

    payload = await request.json()
    topic = payload.get("type") or payload.get("topic") or request.query_params.get("type")
    if topic != "payment":
        return JSONResponse({"status": "ignored"})

    payment_id = (
        payload.get("data", {}).get("id")
        or payload.get("resource", "").rstrip("/").split("/")[-1]
        or payload.get("id")
        or request.query_params.get("data.id")
        or request.query_params.get("id")
    )
    if not payment_id:
        return JSONResponse({"status": "ignored"})

    try:
        await ProcessMercadoPagoWebhookUseCase(
            order_repo=SQLOrderRepository(db),
            mp_service=MercadoPagoService(),
        ).execute(str(payment_id))
    except DomainError:
        return JSONResponse({"status": "ignored"})

    return JSONResponse({"status": "processed"})
