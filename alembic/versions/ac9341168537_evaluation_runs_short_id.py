"""evaluation_runs.short_id, the human-readable RC+date+random run id

B20 identifier model, extended to assessment runs. Today a run is only
addressable by its 36-char UUID; the leaderboard/campaigns screens truncate
it to 8 hex characters for display ("assessment run cdc651b4"), which is
meaningless. Additive per 03-IDENTIFIER-MODEL.md's migration note: the UUID
stays the primary key and foreign-key target, this is a second, unique,
indexed column used only for display and search — same RC + creation date +
random-number shape as campaigns.short_id (see
evaluation_service._next_run_short_id). Existing runs are backfilled from
their own created_at date, with a random suffix checked for collision within
this migration.

Revision ID: ac9341168537
Revises: 1364a83bb0b4
Create Date: 2026-09-13 00:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac9341168537'
down_revision: Union[str, Sequence[str], None] = '1364a83bb0b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluation_runs',
        sa.Column('short_id', sa.String(length=20), nullable=True),
    )
    op.create_index(
        'ix_evaluation_runs_short_id', 'evaluation_runs', ['short_id'], unique=True,
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text('SELECT id, created_at FROM evaluation_runs ORDER BY created_at ASC')
    ).fetchall()
    used = set()
    for row in rows:
        run_id, created_at = row[0], row[1]
        date_part = str(created_at)[:10].replace('-', '') if created_at else '00000000'
        for _ in range(50):
            candidate = f"RC{date_part}-{secrets.randbelow(100000):05d}"
            if candidate not in used:
                used.add(candidate)
                break
        connection.execute(
            sa.text('UPDATE evaluation_runs SET short_id = :short_id WHERE id = :id'),
            {'short_id': candidate, 'id': run_id},
        )


def downgrade() -> None:
    op.drop_index('ix_evaluation_runs_short_id', table_name='evaluation_runs')
    op.drop_column('evaluation_runs', 'short_id')
