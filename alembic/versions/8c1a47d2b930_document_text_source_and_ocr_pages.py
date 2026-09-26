"""document text source and ocr page counts

Records how a document's text was obtained, so an assessment built on text
recovered from an image can be held to a lower confidence ceiling than one
built on a real text layer.

Backfill: existing rows get "extracted", which is true — every document
already in the table was read from a text layer, because until this change
there was no other way for a document to get past intake at all.

`pages_with_text` is left at 0 for existing rows rather than guessed from
`page_count`. A count that was never measured must not be presented as one
that was; `document_quality` reports it as not recorded.

Revision ID: 8c1a47d2b930
Revises: 4f28eb855061
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c1a47d2b930'
down_revision: Union[str, Sequence[str], None] = '4f28eb855061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'candidate_documents',
        sa.Column('text_source', sa.String(length=16), nullable=False,
                  server_default='extracted'),
    )
    op.add_column(
        'candidate_documents',
        sa.Column('pages_with_text', sa.Integer(), nullable=False,
                  server_default='0'),
    )
    op.add_column(
        'candidate_documents',
        sa.Column('ocr_pages', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('candidate_documents', 'ocr_pages')
    op.drop_column('candidate_documents', 'pages_with_text')
    op.drop_column('candidate_documents', 'text_source')
