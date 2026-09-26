"""audit events carry the candidate

An event about a named applicant should be findable by that applicant.
Until now the only candidate reference was `entity_id`, which names whatever
the event is *about* — a batch, a rubric version, a processing job — so
"everything that ever happened to this person" was not a query anyone could
write.

Backfill: existing candidate-scoped rows (entity_type = 'candidate') already
hold the candidate in entity_id, so they are copied across. Every other
existing row leaves candidate_id null, which is true — the candidate was not
recorded at the time and must not be guessed.

Revision ID: c5d91f0a7e42
Revises: 8c1a47d2b930
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d91f0a7e42'
down_revision: Union[str, Sequence[str], None] = '8c1a47d2b930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'audit_events',
        sa.Column('candidate_id', sa.String(length=36), nullable=True),
    )
    op.create_index(
        'ix_audit_events_candidate_id', 'audit_events', ['candidate_id'],
    )
    op.execute(
        "UPDATE audit_events SET candidate_id = entity_id "
        "WHERE entity_type = 'candidate' AND entity_id != ''"
    )


def downgrade() -> None:
    op.drop_index('ix_audit_events_candidate_id', table_name='audit_events')
    op.drop_column('audit_events', 'candidate_id')
