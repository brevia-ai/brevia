"""chat history evaluation

Revision ID: b34017752e45
Revises: 1d927e0cbc61
Create Date: 2024-01-17 11:10:55.127272

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b34017752e45'
down_revision = '1d927e0cbc61'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'chat_history',
        sa.Column(
            'user_evaluation',
            sa.BOOLEAN(),
            nullable=True,
            comment='User evaluation as good (True) or bad (False)',
        ),
    )
    op.add_column(
        'chat_history',
        sa.Column(
            'user_feedback',
            sa.String(),
            nullable=True,
            comment='User textual feedback on the evaluation',
        ),
    )
    op.add_column(
        'chat_history',
        sa.Column(
            'chat_source',
            sa.String(),
            nullable=True,
            comment='Generic string to identify chat source (e.g. application name)',
        ),
    )


def downgrade() -> None:
    op.drop_column('chat_history', 'user_evaluation')
    op.drop_column('chat_history', 'user_feedback')
    op.drop_column('chat_history', 'chat_source')
