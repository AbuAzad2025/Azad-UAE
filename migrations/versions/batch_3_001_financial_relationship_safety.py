"""financial_relationship_safety

Revision ID: batch_3_001
Revises: partner_system_001
Create Date: 2026-06-04 00:15:00.000000

Batch 3: Financial Relationship Safety
- Remove ORM-level cascade on Sale->SaleLine, Purchase->PurchaseLine, GLJournalEntry->GLJournalLine
- Enforce ON DELETE RESTRICT at the database level for these parent->child financial relationships
- Prevents accidental deletion of financial audit history when a parent document is deleted

Rules followed:
1. No financial records are deleted.
2. No cascade delete is added.
3. ON DELETE RESTRICT is preferred.
4. Only confirmed unsafe relationships are fixed.
5. Safe Alembic migration with full rollback support.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'batch_3_001'
down_revision = 'partner_system_001'
branch_labels = None
depends_on = None


def upgrade():
    # ── Sale -> SaleLine ─────────────────────────────────────
    # Drop existing FK (defaults to NO ACTION) and recreate with RESTRICT
    op.drop_constraint('fk_sale_lines_sale_id_sales', 'sale_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_sale_lines_sale_id_sales',
        'sale_lines', 'sales',
        ['sale_id'], ['id'],
        ondelete='RESTRICT'
    )

    # ── Purchase -> PurchaseLine ───────────────────────────────
    op.drop_constraint('fk_purchase_lines_purchase_id_purchases', 'purchase_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_purchase_lines_purchase_id_purchases',
        'purchase_lines', 'purchases',
        ['purchase_id'], ['id'],
        ondelete='RESTRICT'
    )

    # ── GLJournalEntry -> GLJournalLine ──────────────────────
    op.drop_constraint('fk_gl_journal_lines_entry_id_gl_journal_entries', 'gl_journal_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_gl_journal_lines_entry_id_gl_journal_entries',
        'gl_journal_lines', 'gl_journal_entries',
        ['entry_id'], ['id'],
        ondelete='RESTRICT'
    )


def downgrade():
    # ── GLJournalEntry -> GLJournalLine ──────────────────────
    op.drop_constraint('fk_gl_journal_lines_entry_id_gl_journal_entries', 'gl_journal_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_gl_journal_lines_entry_id_gl_journal_entries',
        'gl_journal_lines', 'gl_journal_entries',
        ['entry_id'], ['id']
    )

    # ── Purchase -> PurchaseLine ───────────────────────────────
    op.drop_constraint('fk_purchase_lines_purchase_id_purchases', 'purchase_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_purchase_lines_purchase_id_purchases',
        'purchase_lines', 'purchases',
        ['purchase_id'], ['id']
    )

    # ── Sale -> SaleLine ─────────────────────────────────────
    op.drop_constraint('fk_sale_lines_sale_id_sales', 'sale_lines', type_='foreignkey')
    op.create_foreign_key(
        'fk_sale_lines_sale_id_sales',
        'sale_lines', 'sales',
        ['sale_id'], ['id']
    )
