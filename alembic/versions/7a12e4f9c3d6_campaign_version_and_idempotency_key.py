"""campaign version and idempotency key

B14 backend verification (2026-09-12) found `update_campaign` had no
optimistic-concurrency check and `create_campaign` had no retry/idempotency
protection — two confirmed gaps against the campaign-draft contract in
`docs/contracts/B14-campaign-draft.md`. This adds the two columns backing
those guarantees.

Revision ID: 7a12e4f9c3d6
Revises: d7b3e81c4a05
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a12e4f9c3d6'
down_revision: Union[str, Sequence[str], None] = 'd7b3e81c4a05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'campaigns',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )
    op.add_column(
        'campaigns',
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    )
    op.create_index(
        'ix_campaigns_idempotency_key', 'campaigns', ['idempotency_key'], unique=True
    )


def downgrade() -> None:
    op.drop_index('ix_campaigns_idempotency_key', table_name='campaigns')
    op.drop_column('campaigns', 'idempotency_key')
    op.drop_column('campaigns', 'version')
