from fastapi import APIRouter

from ....config import settings


router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": "1.0.0",
    }
