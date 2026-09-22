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
    from app.models.bill import Bill
    from app.models.product import Product
    from app.models.product_variant import ProductVariant


class BillItem(Base):
    __tablename__ = "bill_items"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ---------------------------------------------------------
    # Bill
    # ---------------------------------------------------------

    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "bills.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Product
    # ---------------------------------------------------------

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "products.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Product Variant
    # ---------------------------------------------------------

    product_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "product_variants.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Historical Product Information
    # ---------------------------------------------------------

    item_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Quantity
    # ---------------------------------------------------------

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Historical Unit Price
    # ---------------------------------------------------------

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Discount
    # ---------------------------------------------------------

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # Historical Tax Rate
    # ---------------------------------------------------------

    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # Tax Amount
    # ---------------------------------------------------------

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # Final Line Total
    # ---------------------------------------------------------

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Timestamp
    # ---------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    bill: Mapped["Bill"] = relationship(
        "Bill",
        back_populates="items",
    )

    product: Mapped["Product | None"] = relationship(
        "Product",
    )

    product_variant: Mapped["ProductVariant | None"] = relationship(
        "ProductVariant",
    )