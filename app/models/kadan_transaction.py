import uuid

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.kadan_account import KadanAccount
    from app.models.bill import Bill
    from app.models.user import User


class KadanTransaction(Base):
    __tablename__ = "kadan_transactions"

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
    # Kadan Account
    # ---------------------------------------------------------

    kadan_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "kadan_accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Related Bill
    # ---------------------------------------------------------

    bill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "bills.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Transaction Type
    # ---------------------------------------------------------

    transaction_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Transaction Amount
    # ---------------------------------------------------------

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Balance After Transaction
    # ---------------------------------------------------------

    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Notes
    # ---------------------------------------------------------

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # User Who Created The Transaction
    # ---------------------------------------------------------

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Timestamp
    # ---------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
    )

    kadan_account: Mapped["KadanAccount"] = relationship(
        "KadanAccount",
        back_populates="transactions",
    )

    bill: Mapped["Bill | None"] = relationship(
        "Bill",
    )

    creator: Mapped["User"] = relationship(
        "User",
    )