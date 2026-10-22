"""add_old_new_values_to_audit_logs

Revision ID: f3cbb888c1eb
Revises: f7955749ce29
Create Date: 2026-09-21 01:24:54.364828
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3cbb888c1eb'
down_revision: Union[str, Sequence[str], None] = 'f7955749ce29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add old_values and new_values JSONB columns to audit_logs."""
    op.add_column(
        'audit_logs',
        sa.Column('old_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove old_values and new_values columns from audit_logs."""
    op.drop_column('audit_logs', 'new_values')
    op.drop_column('audit_logs', 'old_values')