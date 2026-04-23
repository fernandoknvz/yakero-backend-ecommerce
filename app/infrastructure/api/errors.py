from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ...domain.exceptions import DomainError


DOMAIN_ERROR_STATUS = {
    "NOT_FOUND": 404,
    "UNAUTHORIZED": 401,
    "VALIDATION_ERROR": 422,
    "INVALID_TRANSITION": 409,
    "COUPON_ERROR": 400,
    "INSUFFICIENT_POINTS": 400,
    "MODIFIER_REQUIRED": 422,
    "PAYMENT_ERROR": 502,
}


def domain_error_payload(exc: DomainError) -> dict[str, str]:
    return {"code": exc.code, "message": exc.message}


def domain_error_status_code(exc: DomainError) -> int:
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
