"""merge: fix gl_journal_entries index strategy

Revision ID: fefea27bbd9e
Revises: a3d7f1b9c6e2, fix_gl_journal_entries_index_strategy
Create Date: 2026-10-13 19:24:44.204308

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fefea27bbd9e'
down_revision = ('a3d7f1b9c6e2', 'a1b2c3d4')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
