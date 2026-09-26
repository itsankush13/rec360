"""evaluations.ai_rationale_summary, a cached LLM-brief decision draft

B05/B08: the "AI assessment" comment-box draft under Candidate 360's "Your
decision" now calls an LLM to make it brief enough for a non-technical
reader, in disposition_service._suggested_rationale. That draft used to be
recomputed on every page load; since an Evaluation is write-once (see the
model's own docstring), the generated text never goes stale once written, so
it is cached here instead of re-billed on every view. Additive, nullable —
None means "not generated yet", not "empty".

Revision ID: b17e8cfa48d8
Revises: ac9341168537
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b17e8cfa48d8'
down_revision: Union[str, Sequence[str], None] = 'ac9341168537'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluations',
        sa.Column('ai_rationale_summary', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('evaluations', 'ai_rationale_summary')
