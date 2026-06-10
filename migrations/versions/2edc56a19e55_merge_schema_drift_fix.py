"""merge schema drift fix into main line

Revision ID: 2edc56a19e55
Revises: 6f0a6712e08b, b21dada708de
Create Date: 2026-06-10 20:32:00

"""
from alembic import op
import sqlalchemy as sa

revision = '2edc56a19e55'
down_revision = ('6f0a6712e08b', 'b21dada708de')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
