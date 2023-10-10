"""Async jobs table

Revision ID: be67c72a4e5a
Revises: 1eab976dea29
Create Date: 2023-08-03 17:02:05.940720

"""
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision = 'be67c72a4e5a'
down_revision = '1eab976dea29'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'async_jobs',
        sa.Column('uuid', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('service', sa.String(), nullable=False, comment='Service job'),
        sa.Column('payload', sa.JSON(), comment='Input data for this job'),
        sa.Column('expires', sa.TIMESTAMP(timezone=False), comment='Job expiry time'),
        sa.Column(
            'created',
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            server_default=sa.func.current_timestamp(),
            comment='Creation timestamp'
        ),
        sa.Column(
            'completed',
            sa.TIMESTAMP(timezone=False),
            comment='Timestamp at which this job was marked as completed'
        ),
        sa.Column('result', sa.JSON(), nullable=True, comment='Job result'),
    )


def downgrade() -> None:
    op.drop_table('async_jobs')
