import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from ....config import settings
from ...clients import PosClient, PosClientError


router = APIRouter(prefix="/debug", tags=["Debug"])
logger = logging.getLogger(__name__)


@router.get("/mercadopago")
async def debug_mercadopago_config(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _ensure_debug_allowed(x_internal_token)

    frontend_url = settings.resolved_frontend_public_url
    backend_url = settings.resolved_backend_public_url
    notification_url = f"{backend_url}{settings.api_v1_prefix}/payments/webhook"
    warnings = _mercadopago_config_warnings(frontend_url, backend_url, notification_url)

    logger.info(
        "Mercado Pago debug config requested",
        extra={
            "mp_token_exists": bool(settings.mp_access_token),
            "mp_env": settings.mp_env,
            "warning_count": len(warnings),
        },
    )

    return {
        "mp_token_exists": bool(settings.mp_access_token),
        "mp_token_prefix": _token_prefix(settings.mp_access_token),
        "mp_token_length": len(settings.mp_access_token),
        "frontend_url": frontend_url,
        "backend_url": backend_url,
        "success_url": (
            f"{frontend_url}/checkout/success"
            "?external_reference={external_reference}"
            "&checkout_session_id={checkout_session_id}"
        ),
        "failure_url": (
            f"{frontend_url}/checkout/failure"
            "?external_reference={external_reference}"
            "&checkout_session_id={checkout_session_id}"
        ),
        "pending_url": (
            f"{frontend_url}/checkout/pending"
            "?external_reference={external_reference}"
            "&checkout_session_id={checkout_session_id}"
        ),
        "notification_url": notification_url,
        "currency_id": "CLP",
        "environment": settings.mp_env,
        "usa_sandbox_init_point": settings.mp_env == "sandbox",
        "warning": " ".join(warnings) if warnings else None,
        "warnings": warnings,
    }


@router.get("/pos/catalog-summary")
async def debug_pos_catalog_summary(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _ensure_debug_allowed(x_internal_token)

    client = PosClient()
    logger.info(
        "POS catalog summary debug requested",
        extra={"pos_base_url": client.base_url},
    )
    try:
        summary = await client.get_catalog_summary()
    except PosClientError as exc:
        logger.warning(
            "POS catalog summary debug failed status_code=%s provider_status_code=%s message=%s",
            exc.status_code,
            exc.provider_status_code,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "source": "pos",
                "error": exc.message,
            },
        )
    except Exception as exc:
        logger.exception(
            "Unexpected POS catalog summary debug failure exception_type=%s message=%s",
            type(exc).__name__,
            str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "source": "pos",
                "error": "Unexpected POS debug error.",
            },
        )

    return {
        "ok": True,
        "source": "pos",
        "base_url": client.base_url,
        "summary": summary,
    }


def _ensure_debug_allowed(x_internal_token: str | None) -> None:
    if not settings.internal_bootstrap_token:
        raise HTTPException(status_code=503, detail="INTERNAL_BOOTSTRAP_TOKEN no configurado.")
    if not x_internal_token or x_internal_token != settings.internal_bootstrap_token:
        raise HTTPException(status_code=401, detail="Token interno invalido.")


def _token_prefix(token: str) -> str:
    if not token:
        return ""
    if "-" in token:
        return token.split("-", 1)[0]
    return token[:7]


def _mercadopago_config_warnings(
    frontend_url: str,
    backend_url: str,
    notification_url: str,
) -> list[str]:
    warnings: list[str] = []

    if not settings.mp_access_token:
        warnings.append("MP_ACCESS_TOKEN no esta configurado.")
    if settings.mp_env not in {"sandbox", "production"}:
        warnings.append("MP_ENV debe ser sandbox o production.")
    if not frontend_url:
        warnings.append("FRONTEND_PUBLIC_URL o APP_BASE_URL no esta configurado.")
    if not backend_url:
        warnings.append("BACKEND_PUBLIC_URL o API_BASE_URL no esta configurado.")
    if _is_local_url(frontend_url):
        warnings.append("La URL frontend resuelta apunta a localhost; en produccion debe ser publica.")
    if _is_local_url(backend_url):
        warnings.append("La URL backend resuelta apunta a localhost; Mercado Pago requiere una URL publica.")
    if not _is_absolute_url(notification_url):
        warnings.append("notification_url no es absoluta.")
    elif urlparse(notification_url).scheme != "https":
        warnings.append("notification_url debe usar HTTPS para webhooks de Mercado Pago.")
    if settings.mp_env == "production" and settings.mp_access_token.startswith("TEST-"):
        warnings.append("MP_ENV es production pero el token comienza con TEST-.")

    return warnings


def _is_absolute_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)


def _is_local_url(value: str) -> bool:
    hostname = (urlparse(value).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "0.0.0.0"}
