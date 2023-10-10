"""Locked until column

Revision ID: 1d927e0cbc61
Revises: be67c72a4e5a
Create Date: 2023-08-08 12:52:50.336008

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d927e0cbc61'
down_revision = 'be67c72a4e5a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'async_jobs',
        sa.Column(
            'locked_until',
            sa.TIMESTAMP(timezone=False),
            comment='Timestamp at which the lock expires',
        ),
    )
    op.add_column(
        'async_jobs',
        sa.Column(
            'max_attempts',
            sa.SMALLINT(),
            nullable=False,
            server_default='1',
            comment='Maximum number of attempts left for this job'
        ),
    )


def downgrade() -> None:
    op.drop_column('async_jobs', 'locked_until')
    op.drop_column('async_jobs', 'max_attempts')
