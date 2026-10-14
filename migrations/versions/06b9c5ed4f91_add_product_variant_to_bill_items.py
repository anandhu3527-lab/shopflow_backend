"""Add historical offer price to bill items.

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so existing bills remain valid and their offer price is
    # not guessed or fabricated.
    op.add_column(
        "bill_items",
        sa.Column("offer_price", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bill_items", "offer_price")
