"""normalize_legacy_field_values_round1

Revision ID: normalize_legacy_round1_001
Revises: field_quality_round1
Create Date: 2026-06-01 15:00:00.000000

Data-only normalization (safe enum/text):
- payments.payment_type: sale -> sale_payment (all legacy rows had sale_id)
- gl_journal_entries.reference_type: inventory_migration -> InventoryMigration (GLRef canonical)

Downgrade is intentionally limited: reversing sale_payment -> sale would also affect
rows created after this migration. Restore from pg_dump if rollback is required.
"""
from alembic import op
import sqlalchemy as sa


revision = "normalize_legacy_round1_001"
down_revision = "field_quality_round1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "UPDATE payments SET payment_type = 'sale_payment' "
            "WHERE payment_type = 'sale'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE gl_journal_entries SET reference_type = 'InventoryMigration' "
            "WHERE reference_type = 'inventory_migration'"
        )
    )


def downgrade():
    # Not fully reversible without a point-in-time backup (new sale_payment rows must not become 'sale').
    op.execute(
        sa.text(
            "UPDATE gl_journal_entries SET reference_type = 'inventory_migration' "
            "WHERE reference_type = 'InventoryMigration' "
            "AND description ILIKE '%inventory migration%'"
        )
    )
