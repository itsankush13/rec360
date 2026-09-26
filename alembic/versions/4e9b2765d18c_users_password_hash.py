"""users.password_hash for the login gate

B22 phase 1: a real email+password login before the portal, for exactly the
two named accounts today (ankush.saxena, subhadeep.m). Nullable so every
existing seeded user keeps working unauthenticated until a password is set
via scripts/set_password.py.

Revision ID: 4e9b2765d18c
Revises: b4f7c9a1e3d2
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e9b2765d18c'
down_revision: Union[str, Sequence[str], None] = 'b4f7c9a1e3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('password_hash', sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'password_hash')
