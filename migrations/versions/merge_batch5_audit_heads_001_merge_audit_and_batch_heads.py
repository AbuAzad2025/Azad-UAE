"""merge audit trail and batch 5 migration heads

Revision ID: merge_batch5_audit_heads_001
Revises: batch_5_001, audit_trail_001
Create Date: 2026-06-04 09:00:00.000000

This migration has no schema operations. It merges two completed migration
branches so Alembic has a single upgrade head after batches 1-5.
"""
from alembic import op
import sqlalchemy as sa


revision = 'merge_batch5_audit_heads_001'
down_revision = ('batch_5_001', 'audit_trail_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
