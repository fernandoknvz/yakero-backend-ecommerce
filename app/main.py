from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .infrastructure.api.routers.all_routers import (
    auth_router, products_router, categories_router,
    promotions_router, orders_router, users_router,
    delivery_router, coupons_router, webhooks_router, internal_router,
)
from .domain.exceptions import DomainError
from .infrastructure.api.errors import domain_error_to_response

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global error handler ───────────────────────────────────────────────────────
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return domain_error_to_response(exc)

# ── Routers ────────────────────────────────────────────────────────────────────
PREFIX = settings.api_v1_prefix

app.include_router(auth_router,       prefix=PREFIX)
app.include_router(products_router,   prefix=PREFIX)
app.include_router(categories_router, prefix=PREFIX)
app.include_router(promotions_router, prefix=PREFIX)
app.include_router(orders_router,     prefix=PREFIX)
app.include_router(users_router,      prefix=PREFIX)
app.include_router(delivery_router,   prefix=PREFIX)
app.include_router(coupons_router,    prefix=PREFIX)
app.include_router(webhooks_router,   prefix="")      # sin prefijo: /webhooks/mercadopago
app.include_router(internal_router,   prefix=PREFIX)  # /api/v1/internal/...


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": app.version,
    }
