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
    from app.models.product import Product


class ProductVariant(Base):
    __tablename__ = "product_variants"

    # =========================================================
    # Table Constraints
    # =========================================================

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "barcode",
            name="uq_product_variants_tenant_barcode",
        ),
    )

    # =========================================================
    # Primary Key
    # =========================================================

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # =========================================================
    # Tenant
    # =========================================================

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # =========================================================
    # Parent Product
    # =========================================================

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "products.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # =========================================================
    # Package Information
    # =========================================================

    package_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # =========================================================
    # Identification
    # =========================================================

    barcode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    sku: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # =========================================================
    # Pricing
    # =========================================================

    selling_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    offer_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0"),
    )

    # =========================================================
    # Stock
    # =========================================================

    stock_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
    )

    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
    )

    # =========================================================
    # Status
    # =========================================================

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        index=True,
    )

    # =========================================================
    # Timestamps
    # =========================================================

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
    # Product Variant → Product
    # =========================================================

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="variants",
    )