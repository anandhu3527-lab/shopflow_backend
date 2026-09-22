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
    from app.models.user import User
    from app.models.bill_item import BillItem
    from app.models.payment import Payment


class Bill(Base):
    __tablename__ = "bills"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "bill_number",
            name="uq_bills_tenant_bill_number",
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

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Bill Information
    # ---------------------------------------------------------

    bill_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="COMPLETED",
        index=True,
    )

    # ---------------------------------------------------------
    # Created By
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

    customer: Mapped["Customer | None"] = relationship(
        "Customer",
        back_populates="bills",
    )

    creator: Mapped["User"] = relationship(
        "User",
    )

    items: Mapped[list["BillItem"]] = relationship(
        "BillItem",
        back_populates="bill",
        cascade="all, delete-orphan",
    )

    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="bill",
        cascade="all, delete-orphan",
    )