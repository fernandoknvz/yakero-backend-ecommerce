from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ...config import settings
from ...domain.exceptions import DomainError


DOMAIN_ERROR_STATUS = {
    "NOT_FOUND": 404,
    "UNAUTHORIZED": 401,
    "VALIDATION_ERROR": 422,
    "INVALID_TRANSITION": 409,
    "COUPON_ERROR": 400,
    "INSUFFICIENT_POINTS": 400,
    "MODIFIER_REQUIRED": 422,
    "PRODUCT_UNAVAILABLE": 409,
    "INVALID_MODIFIER": 422,
    "INVALID_QUANTITY": 422,
    "ORDER_PRICING_MISMATCH": 409,
    "PAYMENT_ERROR": 502,
}


def domain_error_payload(exc: DomainError) -> dict[str, str]:
    payload = {"code": exc.code, "message": exc.message}
    if settings.debug and getattr(exc, "debug_detail", None):
        payload["debug"] = exc.debug_detail
    return payload


def domain_error_status_code(exc: DomainError) -> int:
    if getattr(exc, "status_code", None):
        return exc.status_code
    return DOMAIN_ERROR_STATUS.get(exc.code, 400)


def domain_error_to_response(exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=domain_error_status_code(exc),
        content=domain_error_payload(exc),
    )


def domain_error_to_http(exc: DomainError) -> HTTPException:
    return HTTPException(
        status_code=domain_error_status_code(exc),
        detail=domain_error_payload(exc),
    )
