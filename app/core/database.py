from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    """
    pass


# ---------------------------------------------------------
# Database URL
# ---------------------------------------------------------

database_url = settings.DATABASE_URL

# Railway may provide:
# postgresql://...
#
# SQLAlchemy async requires:
# postgresql+asyncpg://...
#
# Convert automatically when necessary.
if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )


# ---------------------------------------------------------
# Database Engine
# ---------------------------------------------------------

engine = create_async_engine(
    database_url,

    # IMPORTANT:
    # SQL queries are logged only during local development.
    #
    # Development:
    #     APP_ENV=development → SQL logging ON
    #
    # Production/Railway:
    #     APP_ENV=production → SQL logging OFF
    #
    echo=(settings.APP_ENV == "development"),

    # Prevent the engine from holding too many connections.
    # These values are intentionally conservative for the
    # current ShopFlow pilot.
    pool_size=5,
    max_overflow=5,

    # Check that an existing connection is still alive
    # before using it.
    pool_pre_ping=True,

    # Recycle long-lived connections periodically.
    pool_recycle=1800,
)


# ---------------------------------------------------------
# Async Session Factory
# ---------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------
# FastAPI Database Dependency
# ---------------------------------------------------------

async def get_db():
    """
    Provides an AsyncSession to FastAPI endpoints.

    The session is automatically closed after the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
