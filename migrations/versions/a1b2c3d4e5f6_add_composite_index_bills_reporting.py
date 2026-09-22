"""add composite index on bills for reporting

Revision ID: a1b2c3d4e5f6
Revises: f3cbb888c1eb
Create Date: 2026-09-22 20:51:00.000000

Adds a composite index on bills(tenant_id, status, created_at) to support
the most-sold product reporting queries which filter on all three columns
simultaneously. This replaces three individual single-column index scans
with a single efficient composite index scan.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3cbb888c1eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite index for reporting queries on bills."""
    op.create_index(
        'ix_bills_tenant_status_created',
        'bills',
        ['tenant_id', 'status', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Remove composite index."""
    op.drop_index('ix_bills_tenant_status_created', table_name='bills')
