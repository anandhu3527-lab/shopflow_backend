"""create bill_item table

Revision ID: 9f89a2930665
Revises: 6886d3ec1b73
Create Date: 2026-09-10 23:48:52.110482
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9f89a2930665"
down_revision: Union[str, Sequence[str], None] = "6886d3ec1b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op.

    bill_items is created in the product migration
    (269337f4c33a), after the products table exists.
    """
    pass


def downgrade() -> None:
    """No-op."""
    pass
