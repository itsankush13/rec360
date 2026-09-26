"""cost centres, delegation grants, llm call logs

B13 (cost-centre controls and delegation of authority): `cost_centres` is the
registry an approval's cost-centre code and claimed budget holder are
validated against — previously neither was checked against anything.
`delegation_grants` is the ledger `on_behalf_of_id` (on `lifecycle_transitions`,
already present) is checked against — previously nothing verified a claimed
delegation was real. `candidate_lifecycle.cost_centre_id` and
`whatif_proposals.draft_version_id` are the two small additive columns that
go with them.

B21 (FinOps): `llm_call_logs` is one row per recorded model call, the basis
for `/api/developer/metrics`.

Revision ID: b4f7c9a1e3d2
Revises: 9d3f6b1a4c72
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f7c9a1e3d2'
down_revision: Union[str, Sequence[str], None] = '9d3f6b1a4c72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cost_centres',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('budget_holder_id', sa.String(length=36), nullable=False),
        sa.Column('annual_budget_usd', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_cost_centres_code'), 'cost_centres', ['code'], unique=True,
    )

    op.create_table(
        'delegation_grants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('grantor_id', sa.String(length=36), nullable=False),
        sa.Column('delegate_id', sa.String(length=36), nullable=False),
        sa.Column('scope', sa.String(length=40), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_delegation_grants_grantor_id'), 'delegation_grants', ['grantor_id'],
    )
    op.create_index(
        op.f('ix_delegation_grants_delegate_id'), 'delegation_grants', ['delegate_id'],
    )
    op.create_index(
        op.f('ix_delegation_grants_campaign_id'), 'delegation_grants', ['campaign_id'],
    )

    op.create_table(
        'llm_call_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=True),
        sa.Column('call_type', sa.String(length=40), nullable=False),
        sa.Column('model_name', sa.String(length=120), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_llm_call_logs_campaign_id'), 'llm_call_logs', ['campaign_id'],
    )
    op.create_index(
        op.f('ix_llm_call_logs_run_id'), 'llm_call_logs', ['run_id'],
    )
    op.create_index(
        op.f('ix_llm_call_logs_created_at'), 'llm_call_logs', ['created_at'],
    )

    op.add_column(
        'candidate_lifecycle',
        sa.Column('cost_centre_id', sa.String(length=36), nullable=True),
    )
    op.add_column(
        'whatif_proposals',
        sa.Column('draft_version_id', sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('whatif_proposals', 'draft_version_id')
    op.drop_column('candidate_lifecycle', 'cost_centre_id')

    op.drop_index(op.f('ix_llm_call_logs_created_at'), table_name='llm_call_logs')
    op.drop_index(op.f('ix_llm_call_logs_run_id'), table_name='llm_call_logs')
    op.drop_index(op.f('ix_llm_call_logs_campaign_id'), table_name='llm_call_logs')
    op.drop_table('llm_call_logs')

    op.drop_index(op.f('ix_delegation_grants_campaign_id'), table_name='delegation_grants')
    op.drop_index(op.f('ix_delegation_grants_delegate_id'), table_name='delegation_grants')
    op.drop_index(op.f('ix_delegation_grants_grantor_id'), table_name='delegation_grants')
    op.drop_table('delegation_grants')

    op.drop_index(op.f('ix_cost_centres_code'), table_name='cost_centres')
    op.drop_table('cost_centres')
