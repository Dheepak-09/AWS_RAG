"""add user table and user_id to sessions

Revision ID: 577d61395a3a
Revises: 
Create Date: 2026-05-07 23:32:43.485898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '577d61395a3a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import uuid

def upgrade():
    # Create users table
    op.create_table('users',
        sa.Column('user_id',    sa.UUID(), nullable=False),
        sa.Column('email',      sa.String(), nullable=False),
        sa.Column('password',   sa.String(), nullable=False),
        sa.Column('role',       sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('email')
    )

    # Add user_id as nullable first
    op.add_column('sessions', sa.Column('user_id', sa.UUID(), nullable=True))

    # Now make it NOT NULL — safe because we just deleted all rows
    op.alter_column('sessions', 'user_id', nullable=False)

    # Add foreign key
    op.create_foreign_key(
        'fk_sessions_user_id',
        'sessions', 'users',
        ['user_id'], ['user_id']
    )


def downgrade():
    op.drop_constraint('fk_sessions_user_id', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'user_id')
    op.drop_table('users')
