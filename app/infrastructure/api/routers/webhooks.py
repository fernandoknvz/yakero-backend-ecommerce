from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.session import get_db
from ....config import settings
from .payments import (
    SQLAddressRepository,
    SQLCheckoutSessionRepository,
    SQLCouponRepository,
    SQLOrderRepository,
    SQLPaymentRepository,
    SQLProductRepository,
    SQLPromotionRepository,
    SQLUserRepository,
    MercadoPagoService,
    process_mercadopago_webhook_request,
)


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/mercadopago", deprecated=True)
async def mp_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await process_mercadopago_webhook_request(
        request,
        x_signature,
        db,
        deprecated_route=True,
    )
