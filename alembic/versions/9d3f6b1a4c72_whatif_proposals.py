"""whatif proposals

B17 (what-if analysis): a recruiter's proposed rubric reweighting, sent to a
named hiring manager for a decision. Separate from the free, non-persisting
preview in app.core.analytics.what_if() — approving a proposal authorizes
proceeding to a real rubric revision, it does not create one.

Revision ID: 9d3f6b1a4c72
Revises: 2a13836a93f4
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d3f6b1a4c72'
down_revision: Union[str, Sequence[str], None] = '2a13836a93f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatif_proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('rubric_version_id', sa.String(length=36), nullable=False),
        sa.Column('proposed_weights', sa.JSON(), nullable=False),
        sa.Column('approved_weights', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('proposed_by', sa.String(length=36), nullable=False),
        sa.Column('approver_id', sa.String(length=36), nullable=False),
        sa.Column('decided_by', sa.String(length=36), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id']),
        sa.ForeignKeyConstraint(['rubric_version_id'], ['rubric_versions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_whatif_proposals_campaign_id'), 'whatif_proposals', ['campaign_id'],
    )
    op.create_index(
        op.f('ix_whatif_proposals_rubric_version_id'), 'whatif_proposals', ['rubric_version_id'],
    )
    op.create_index(
        op.f('ix_whatif_proposals_status'), 'whatif_proposals', ['status'],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_whatif_proposals_status'), table_name='whatif_proposals')
    op.drop_index(op.f('ix_whatif_proposals_rubric_version_id'), table_name='whatif_proposals')
    op.drop_index(op.f('ix_whatif_proposals_campaign_id'), table_name='whatif_proposals')
    op.drop_table('whatif_proposals')
