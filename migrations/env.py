from logging.config import fileConfig

import asyncio

from alembic import context

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base


# ---------------------------------------------------------
# Import all models
# ---------------------------------------------------------
#
# These imports ensure SQLAlchemy registers all model
# tables in Base.metadata before Alembic compares them
# with the database.
#

from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole

from app.models.category import Category

from app.models.product import Product
from app.models.product_variant import ProductVariant

from app.models.customer import Customer

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.payment import Payment

from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction

from app.models.audit_log import AuditLog
from app.models.subscription import Subscription


# ---------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------

config = context.config


# ---------------------------------------------------------
# Set up Python logging from alembic.ini
# ---------------------------------------------------------

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------
# SQLAlchemy metadata
# ---------------------------------------------------------
#
# Alembic uses this metadata to detect model changes.
#

target_metadata = Base.metadata


# ---------------------------------------------------------
# Database URL
# ---------------------------------------------------------
#
# Load DATABASE_URL from .env through our Settings class.
#

config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("%", "%%"),
)


# ---------------------------------------------------------
# Offline migrations
# ---------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations without connecting to the database.
    """

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------
# Online migration helper
# ---------------------------------------------------------

def do_run_migrations(connection) -> None:
    """
    Run migrations using an active database connection.
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------
# Async migration runner
# ---------------------------------------------------------

async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations.
    """

    connectable = async_engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            do_run_migrations
        )

    await connectable.dispose()


# ---------------------------------------------------------
# Online migrations
# ---------------------------------------------------------

def run_migrations_online() -> None:
    """
    Run migrations with a database connection.
    """

    asyncio.run(
        run_async_migrations()
    )


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()