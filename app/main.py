from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .domain.exceptions import DomainError
from .infrastructure.api.errors import domain_error_to_response
from .infrastructure.api.routers import PUBLIC_ROUTERS, VERSIONED_ROUTERS


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    diagnostics = settings.public_runtime_diagnostics()
    if diagnostics["jwt_insecure"] and not settings.is_production:
        logger.warning("Running with insecure JWT secret outside production.")
    logger.info("Starting Yakero backend with diagnostics: %s", diagnostics)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return domain_error_to_response(exc)


for router in VERSIONED_ROUTERS:
    app.include_router(router, prefix=settings.api_v1_prefix)

for router in PUBLIC_ROUTERS:
    app.include_router(router)
