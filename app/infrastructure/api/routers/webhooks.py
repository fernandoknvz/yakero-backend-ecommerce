from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLOrderRepository
from ...database.session import get_db
from ...payment.mercadopago_service import MercadoPagoService
from ....application.use_cases.orders.order_use_cases import ConfirmPaymentUseCase
from ....config import settings

import mercadopago


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/mercadopago")
async def mp_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    mp_service = MercadoPagoService()

    if x_signature and not settings.mp_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret no configurado")
    if x_signature and not mp_service.verify_webhook_signature(body.decode(), x_signature):
        raise HTTPException(status_code=401, detail="Firma de webhook invalida")

    payload = await request.json()
    topic = payload.get("type") or payload.get("topic")
    if topic != "payment":
        return JSONResponse({"status": "ignored"})

    payment_id = str(payload.get("data", {}).get("id") or payload.get("id", ""))
    if not payment_id:
        return JSONResponse({"status": "no payment id"})

    sdk = mercadopago.SDK(settings.mp_access_token)
    payment_info = sdk.payment().get(payment_id)
    payment_data = payment_info.get("response", {})
    preference_id = payment_data.get("order", {}).get("id") or payment_data.get("preference_id", "")
    mp_status = payment_data.get("status", "")

    await ConfirmPaymentUseCase(SQLOrderRepository(db)).execute(
        preference_id=preference_id,
        mp_payment_id=payment_id,
        mp_status=mp_status,
    )
    return JSONResponse({"status": "processed"})
