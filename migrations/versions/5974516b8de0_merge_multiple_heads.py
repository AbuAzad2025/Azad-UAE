"""Merge multiple heads

Revision ID: 5974516b8de0
Revises: fb38b4dfe43b, gl_mapping_004_update_ck_constraint, negative_inventory_001
Create Date: 2026-06-21 22:47:19.070023

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5974516b8de0'
down_revision = ('fb38b4dfe43b', 'gl_mapping_004_update_ck_constraint', 'negative_inventory_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
