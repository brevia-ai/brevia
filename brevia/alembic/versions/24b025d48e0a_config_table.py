"""config table

Revision ID: 24b025d48e0a
Revises: 95d93297832c
Create Date: 2024-10-11 10:19:27.308907

"""
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision = '24b025d48e0a'
down_revision = '95d93297832c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'config',
        sa.Column('uuid', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            'config_key',
            sa.String(),
            nullable=False,
            comment='Configuration name'
        ),
        sa.Column(
            'config_val',
            sa.String(),
            nullable=False,
            comment='Configuration value'
        ),
        sa.Column(
            'created',
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            server_default=sa.func.current_timestamp(),
            comment='Creation timestamp'
        ),
        sa.Column(
            'modified',
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            server_default=sa.func.current_timestamp(),
            onupdate=sa.func.current_timestamp(),
            comment='Last update timestamp'
        ),
    )


def downgrade() -> None:
    op.drop_table('config')
