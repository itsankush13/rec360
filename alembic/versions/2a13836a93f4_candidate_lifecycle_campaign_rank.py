"""candidate lifecycle campaign rank

B15 (historical candidate reuse): preserve the leaderboard rank a candidate
held at the moment they entered the lifecycle (shortlisted or waitlisted),
so a later re-evaluation moving scores around cannot retroactively change
the ranking a decision was actually made against.

Revision ID: 2a13836a93f4
Revises: 7a12e4f9c3d6
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a13836a93f4'
down_revision: Union[str, Sequence[str], None] = '7a12e4f9c3d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'candidate_lifecycle',
        sa.Column('campaign_rank', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('candidate_lifecycle', 'campaign_rank')
