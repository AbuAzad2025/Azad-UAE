"""fix_nullability_mismatches

Revision ID: batch_5_001
Revises: batch_4_001
Create Date: 2026-06-04 08:20:00.000000

Batch 5: Model/Migration Sync
Align database nullability with model definitions for two confirmed mismatches:

1. cheques.tenant_id  — model says nullable=False, DB says YES
2. partners.is_active — model says nullable=False, DB says YES

Pre-migration validation: both columns contain zero NULL values,
so no backfill is required.

Safety: Uses ALTER COLUMN with explicit NOT NULL.
Downgrade: Reverts to nullable.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'batch_5_001'
down_revision = 'batch_4_001'
branch_labels = None
depends_on = None


def upgrade():
    # ── cheques.tenant_id ───────────────────────────────────
    op.alter_column('cheques', 'tenant_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)

    # ── partners.is_active ────────────────────────────────
    op.alter_column('partners', 'is_active',
                    existing_type=sa.BOOLEAN(),
                    nullable=False,
                    server_default='true')


def downgrade():
    # ── partners.is_active ────────────────────────────────
    op.alter_column('partners', 'is_active',
                    existing_type=sa.BOOLEAN(),
                    nullable=True)

    # ── cheques.tenant_id ───────────────────────────────────
    op.alter_column('cheques', 'tenant_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)
