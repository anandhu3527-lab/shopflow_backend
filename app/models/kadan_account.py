import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.customer import Customer
    from app.models.kadan_transaction import KadanTransaction


class KadanAccount(Base):
    __tablename__ = "kadan_accounts"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "customer_id",
            name="uq_kadan_accounts_tenant_customer",
        ),
    )

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ---------------------------------------------------------
    # Tenant
    # ---------------------------------------------------------

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Customer
    # ---------------------------------------------------------

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Kadan Information
    # ---------------------------------------------------------

    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        index=True,
    )

    # ---------------------------------------------------------
    # Timestamps
    # ---------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================================================
    # Relationships
    # =========================================================

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="kadan_account",
    )

    transactions: Mapped[list["KadanTransaction"]] = relationship(
        "KadanTransaction",
        back_populates="kadan_account",
        cascade="all, delete-orphan",
    )