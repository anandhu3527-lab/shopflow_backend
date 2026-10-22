import uuid

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.bill import Bill
    from app.models.user import User


class Payment(Base):
    __tablename__ = "payments"

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
    # Bill
    # ---------------------------------------------------------

    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "bills.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Payment Amount
    # ---------------------------------------------------------

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Payment Method
    # ---------------------------------------------------------

    payment_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Payment Status
    # ---------------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="COMPLETED",
        index=True,
    )

    # ---------------------------------------------------------
    # User Who Created The Payment
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
    # Timestamps
    # ---------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
    )

    bill: Mapped["Bill"] = relationship(
        "Bill",
        back_populates="payments",
    )

    creator: Mapped["User"] = relationship(
        "User",
    )