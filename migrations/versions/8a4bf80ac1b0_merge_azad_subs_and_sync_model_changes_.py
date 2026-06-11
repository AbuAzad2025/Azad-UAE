"""Merge azad_subs and sync_model_changes heads

Revision ID: 8a4bf80ac1b0
Revises: azad_subs_001, c98e9930ce80
Create Date: 2026-06-11 17:44:32.047240

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a4bf80ac1b0'
down_revision = ('azad_subs_001', 'c98e9930ce80')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
