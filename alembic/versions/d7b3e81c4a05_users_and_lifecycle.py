"""users and the recruitment lifecycle

Phase 0 and phase 1 of workstream 7. Identity, the state machine, and the
hiring manager's review.

`users` deliberately does not extend `tenants.db`, the separate SQLite
database behind `app/core/auth.py`. That file belongs to the legacy Streamlit
app, is imported nowhere in `app/`, and is not managed by Alembic. Putting
identity in two places would guarantee they eventually disagree about who is
allowed to approve what.

Revision ID: d7b3e81c4a05
Revises: c5d91f0a7e42
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7b3e81c4a05'
down_revision: Union[str, Sequence[str], None] = 'c5d91f0a7e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('role', sa.Enum(
            'RECRUITER', 'HIRING_MANAGER', 'REVIEWER', 'ADMIN',
            name='userrole', native_enum=False, length=20), nullable=False),
        sa.Column('business_unit', sa.String(length=120), nullable=True),
        # Deactivated rather than deleted: a person who has approved
        # something must stay nameable for as long as that approval stands.
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'candidate_lifecycle',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('current_owner_id', sa.String(length=36), nullable=True),
        sa.Column('entered_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('held_from_status', sa.String(length=30), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id']),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_candidate_lifecycle_campaign_id', 'candidate_lifecycle', ['campaign_id'])
    op.create_index('ix_candidate_lifecycle_candidate_id', 'candidate_lifecycle', ['candidate_id'])
    op.create_index('ix_candidate_lifecycle_status', 'candidate_lifecycle', ['status'])
    op.create_index('ix_candidate_lifecycle_is_current', 'candidate_lifecycle', ['is_current'])
    op.create_index('ix_candidate_lifecycle_current_owner_id', 'candidate_lifecycle', ['current_owner_id'])

    op.create_table(
        'lifecycle_transitions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), nullable=False),
        sa.Column('from_status', sa.String(length=30), nullable=True),
        sa.Column('to_status', sa.String(length=30), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=True),
        # Delegation is a column from the start, so the approval work can
        # fill it without a migration or a contract change.
        sa.Column('on_behalf_of_id', sa.String(length=36), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lifecycle_transitions_campaign_id', 'lifecycle_transitions', ['campaign_id'])
    op.create_index('ix_lifecycle_transitions_candidate_id', 'lifecycle_transitions', ['candidate_id'])
    op.create_index('ix_lifecycle_transitions_created_at', 'lifecycle_transitions', ['created_at'])

    op.create_table(
        'manager_reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), nullable=False),
        # Pinned to the assessment the manager was shown, so a later
        # re-assessment cannot retrospectively change what was decided on.
        sa.Column('evaluation_id', sa.String(length=36), nullable=True),
        sa.Column('reviewer_id', sa.String(length=36), nullable=False),
        sa.Column('outcome', sa.Enum(
            'PROCEED', 'DECLINE', 'QUESTION',
            name='managerreviewoutcome', native_enum=False, length=20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_manager_reviews_campaign_id', 'manager_reviews', ['campaign_id'])
    op.create_index('ix_manager_reviews_candidate_id', 'manager_reviews', ['candidate_id'])
    op.create_index('ix_manager_reviews_reviewer_id', 'manager_reviews', ['reviewer_id'])


def downgrade() -> None:
    op.drop_table('manager_reviews')
    op.drop_table('lifecycle_transitions')
    op.drop_table('candidate_lifecycle')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
