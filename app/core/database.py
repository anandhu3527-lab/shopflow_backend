from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Railway provides PostgreSQL connection URLs as:
# postgresql://...
#
# SQLAlchemy async requires:
# postgresql+asyncpg://...
#
# Keep local development and Railway deployment compatible.
database_url = settings.DATABASE_URL

if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )


engine = create_async_engine(
    database_url,
    echo=(settings.APP_ENV == "development"),
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
