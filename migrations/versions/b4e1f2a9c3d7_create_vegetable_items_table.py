"""create vegetable_items table

Revision ID: b4e1f2a9c3d7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-26 17:30:00.000000

Adds the vegetable_items table that stores per-weight pricing and stock
for products that do not use package variants.  This is an additive
migration; no existing tables, columns, or constraints are changed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b4e1f2a9c3d7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the vegetable_items table."""
    op.create_table(
        "vegetable_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit",
            sa.String(length=20),
            nullable=False,
            server_default="kg",
        ),
        sa.Column(
            "price_per_kg",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "tax_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "stock_kg",
            sa.Numeric(precision=12, scale=3),
            nullable=False,
            server_default="0.000",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "product_id",
            name="uq_vegetable_items_tenant_product",
        ),
    )

    op.create_index(
        "ix_vegetable_items_tenant_id",
        "vegetable_items",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_vegetable_items_product_id",
        "vegetable_items",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_vegetable_items_status",
        "vegetable_items",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the vegetable_items table and its indexes."""
    op.drop_index("ix_vegetable_items_status", table_name="vegetable_items")
    op.drop_index("ix_vegetable_items_product_id", table_name="vegetable_items")
    op.drop_index("ix_vegetable_items_tenant_id", table_name="vegetable_items")
    op.drop_table("vegetable_items")
