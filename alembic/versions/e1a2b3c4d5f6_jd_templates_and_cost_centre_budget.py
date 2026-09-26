"""jd templates and cost centre budget-envelope fields

Demo-readiness pass, 2026-09-14. `jd_templates` is the smallest honest JD
library: a saved, reusable JD independent of any campaign. The new
`cost_centres` columns (`business_unit`, `currency`, `fiscal_year`,
`role_grade`, `approved_headcount`, `salary_band_min/max`) hold the BU-level
pre-approved requisition envelope the approvals page needs to show — all
nullable/additive, existing rows and the pre-existing `annual_budget_usd`
column are untouched.

Revision ID: e1a2b3c4d5f6
Revises: b17e8cfa48d8
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, Sequence[str], None] = 'b17e8cfa48d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jd_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('role_title', sa.String(length=200), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('tags', sa.String(length=300), nullable=False),
        sa.Column('source_file', sa.String(length=300), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('cost_centres') as batch_op:
        batch_op.add_column(sa.Column('business_unit', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'))
        batch_op.add_column(sa.Column('fiscal_year', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('role_grade', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('approved_headcount', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('salary_band_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('salary_band_max', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cost_centres') as batch_op:
        batch_op.drop_column('salary_band_max')
        batch_op.drop_column('salary_band_min')
        batch_op.drop_column('approved_headcount')
        batch_op.drop_column('role_grade')
        batch_op.drop_column('fiscal_year')
        batch_op.drop_column('currency')
        batch_op.drop_column('business_unit')

    op.drop_table('jd_templates')
