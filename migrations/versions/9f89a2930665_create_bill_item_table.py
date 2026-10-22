"""create bill_item table

Revision ID: 9f89a2930665
Revises: 6886d3ec1b73
Create Date: 2026-09-10 23:48:52.110482

This migration is intentionally a no-op.

The bill_items table is created by the product migration:
269337f4c33a_create_product_table.py

That migration creates the products table first and then creates
bill_items with its foreign key to products.id.

Keeping this migration as a no-op prevents bill_items from being
created before the products table exists.
"""

from typing import Sequence, Union

from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "9f89a2930665"
down_revision: Union[str, Sequence[str], None] = "6886d3ec1b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Intentionally empty.

    The bill_items table is created later by:
    269337f4c33a_create_product_table.py
    """
    pass


def downgrade() -> None:
    """
    Intentionally empty.

    The bill_items table is managed by the product migration.
    """
    pass
