"""Merge phase5_001 and security_7_5_001 migration heads

Revision ID: merge_phase5_security_7_5
Revises: phase5_001, security_7_5_001
Create Date: 2026-06-06 10:55:58

This migration resolves the Alembic branch created when
security_7_5_001_add_tenant_id_to_donation_vault.py was based on
phase5_001 rather than the merge head.
"""
from alembic import op
import sqlalchemy as sa


revision = 'merge_phase5_security_7_5'
down_revision = ('phase5_001', 'security_7_5_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
