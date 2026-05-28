import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from ...config import settings
from .connection import build_async_engine_config, database_connection_diagnostics, has_ssl_context


logger = logging.getLogger(__name__)

engine_kwargs = {
    "echo": settings.debug,
    "pool_pre_ping": True,
}
if settings.testing:
    engine_kwargs["poolclass"] = NullPool

engine_url, engine_kwargs = build_async_engine_config(settings.database_url, **engine_kwargs)
logger.info(
    "Creating async database engine: %s",
    database_connection_diagnostics(settings.database_url, has_ssl_context(engine_kwargs)),
)
engine = create_async_engine(engine_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
