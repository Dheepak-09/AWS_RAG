"""remove users table and FK from sessions

Revision ID: 01a16d9d9d7c
Revises: 516b7fea0d86
Create Date: 2026-05-07 23:59:44.358185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '01a16d9d9d7c'
down_revision: Union[str, Sequence[str], None] = '516b7fea0d86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK constraint from sessions
    op.drop_constraint(op.f('sessions_user_id_fkey'), 'sessions', type_='foreignkey')
    # Drop users table
    op.drop_table('users')
    # rag_documents is intentionally left alone — managed by psycopg2 directly


def downgrade() -> None:
    op.create_foreign_key(op.f('sessions_user_id_fkey'), 'sessions', 'users', ['user_id'], ['user_id'])
    op.create_table('users',
        sa.Column('user_id',    sa.UUID(), nullable=False),
        sa.Column('email',      sa.VARCHAR(), nullable=False),
        sa.Column('password',   sa.VARCHAR(), nullable=False),
        sa.Column('role',       sa.VARCHAR(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('email')
    )
