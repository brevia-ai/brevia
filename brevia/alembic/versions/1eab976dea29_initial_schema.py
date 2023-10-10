"""Initial schema

Revision ID: 1eab976dea29
Revises:
Create Date: 2023-08-02 19:05:29.656326

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
import uuid

# revision identifiers, used by Alembic.
revision = '1eab976dea29'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    conn = op.get_bind()
    conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))

    op.create_table(
        'langchain_pg_collection',
        sa.Column('uuid', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('cmetadata', sa.JSON(), nullable=True),
    )

    op.create_table(
        'langchain_pg_embedding',
        sa.Column('uuid', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('collection_id', sa.UUID()),
        sa.Column('embedding', Vector()),
        sa.Column('document', sa.String(), nullable=True),
        sa.Column('cmetadata', sa.JSON(), nullable=True),
        sa.Column('custom_id', sa.String(), nullable=True),
    )
    op.create_foreign_key(
        constraint_name='langchain_pg_embedding_collection_id_fkey',
        source_table='langchain_pg_embedding',
        referent_table='langchain_pg_collection',
        local_cols=['collection_id'],
        remote_cols=['uuid'],
        onupdate='NO ACTION',
        ondelete='CASCADE',
    )

    op.create_table(
        'chat_history',
        sa.Column('uuid', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('collection_id', sa.UUID()),
        sa.Column('question', sa.String()),
        sa.Column('answer', sa.String()),
        sa.Column(
            'created',
            sa.TIMESTAMP(timezone=False),
            server_default=sa.func.current_timestamp()
        ),
        sa.Column('cmetadata', sa.JSON(), nullable=True),
    )
    op.create_foreign_key(
        constraint_name='chat_history_collection_id_fkey',
        source_table='chat_history',
        referent_table='langchain_pg_collection',
        local_cols=['collection_id'],
        remote_cols=['uuid'],
        onupdate='NO ACTION',
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_table('langchain_pg_embedding')
    op.drop_table('chat_history')
    op.drop_table('langchain_pg_collection')
