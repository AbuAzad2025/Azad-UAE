"""add_tenant_scoping_advanced_accounting (corrected)

Revision ID: tenant_scope_003
Revises: partner_system_001
Create Date: 2026-06-03 23:58:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'tenant_scope_003'
down_revision = 'partner_system_001'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add tenant_id columns as nullable initially
    op.add_column('customs_taxes', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.add_column('advanced_expenses', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.add_column('tax_calculation_rules', sa.Column('tenant_id', sa.Integer(), nullable=True))

    # 2. Safe Backfill Phase: Infer tenant_id from related entities
    
    # 2.1 Backfill customs_taxes from gl_accounts
    op.execute("""
        UPDATE customs_taxes t
        SET tenant_id = a.tenant_id
        FROM gl_accounts a
        WHERE t.gl_account_id = a.id AND t.tenant_id IS NULL
    """)

    # 2.2 Backfill advanced_expenses from branches
    op.execute("""
        UPDATE advanced_expenses e
        SET tenant_id = b.tenant_id
        FROM branches b
        WHERE e.branch_id = b.id AND e.tenant_id IS NULL
    """)

    # 2.3 Backfill advanced_expenses from gl_journal_entries (if branch mapping missed)
    op.execute("""
        UPDATE advanced_expenses e
        SET tenant_id = j.tenant_id
        FROM gl_journal_entries j
        WHERE e.gl_journal_entry_id = j.id AND e.tenant_id IS NULL
    """)

    # 2.4 Backfill advanced_expenses from users (created_by) (if still null)
    op.execute("""
        UPDATE advanced_expenses e
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE e.created_by = u.id AND e.tenant_id IS NULL
    """)

    # 2.5 Backfill tax_calculation_rules from customs_taxes (now that it is filled)
    op.execute("""
        UPDATE tax_calculation_rules r
        SET tenant_id = t.tenant_id
        FROM customs_taxes t
        WHERE r.tax_id = t.id AND r.tenant_id IS NULL
    """)

    # 3. Validation Phase: Ensure no rows remain unmapped
    conn = op.get_bind()
    for table in ['customs_taxes', 'advanced_expenses', 'tax_calculation_rules']:
        # Fetch up to 10 IDs to report in error message
        unmapped = conn.execute(sa.text(f"SELECT id FROM {table} WHERE tenant_id IS NULL LIMIT 10")).all()
        if unmapped:
            ids = [str(r[0]) for r in unmapped]
            count = conn.execute(sa.text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")).scalar()
            raise RuntimeError(
                f"CRITICAL SAFETY ABORT: Found {count} unmapped rows in '{table}' (Sample IDs: {', '.join(ids)}). "
                f"These rows cannot be automatically associated with a tenant. "
                f"Assign tenant_id manually for these rows in the database before running this migration again."
            )

    # 4. Alter columns to NOT NULL only after validation passes
    op.alter_column('customs_taxes', 'tenant_id', nullable=False)
    op.alter_column('advanced_expenses', 'tenant_id', nullable=False)
    op.alter_column('tax_calculation_rules', 'tenant_id', nullable=False)

    # 5. Add foreign key constraints with explicit names
    op.create_foreign_key('fk_customs_taxes_tenant_id', 'customs_taxes', 'tenants', ['tenant_id'], ['id'])
    op.create_foreign_key('fk_advanced_expenses_tenant_id', 'advanced_expenses', 'tenants', ['tenant_id'], ['id'])
    op.create_foreign_key('fk_tax_calculation_rules_tenant_id', 'tax_calculation_rules', 'tenants', ['tenant_id'], ['id'])

    # 6. Add indexes on tenant_id
    op.create_index('ix_customs_taxes_tenant_id', 'customs_taxes', ['tenant_id'])
    op.create_index('ix_advanced_expenses_tenant_id', 'advanced_expenses', ['tenant_id'])
    op.create_index('ix_tax_calculation_rules_tenant_id', 'tax_calculation_rules', ['tenant_id'])

    # 7. Update AdvancedExpense UniqueConstraint
    # First, drop the old global unique index/constraint
    op.drop_index('ix_advanced_expenses_expense_number', table_name='advanced_expenses')
    # Re-create it as a non-unique index
    op.create_index('ix_advanced_expenses_expense_number', 'advanced_expenses', ['expense_number'], unique=False)
    # Add the new multi-column unique constraint
    op.create_unique_constraint('uq_advanced_expenses_tenant_number', 'advanced_expenses', ['tenant_id', 'expense_number'])


def downgrade():
    # 1. Drop multi-column unique constraint
    op.drop_constraint('uq_advanced_expenses_tenant_number', 'advanced_expenses', type_='unique')
    
    # 2. Restore global unique index on expense_number
    op.drop_index('ix_advanced_expenses_expense_number', table_name='advanced_expenses')
    op.create_index('ix_advanced_expenses_expense_number', 'advanced_expenses', ['expense_number'], unique=True)

    # 3. Drop indexes on tenant_id
    op.drop_index('ix_tax_calculation_rules_tenant_id', table_name='tax_calculation_rules')
    op.drop_index('ix_advanced_expenses_tenant_id', table_name='advanced_expenses')
    op.drop_index('ix_customs_taxes_tenant_id', table_name='customs_taxes')

    # 4. Drop foreign keys
    op.drop_constraint('fk_tax_calculation_rules_tenant_id', 'tax_calculation_rules', type_='foreignkey')
    op.drop_constraint('fk_advanced_expenses_tenant_id', 'advanced_expenses', type_='foreignkey')
    op.drop_constraint('fk_customs_taxes_tenant_id', 'customs_taxes', type_='foreignkey')

    # 5. Remove columns
    op.drop_column('tax_calculation_rules', 'tenant_id')
    op.drop_column('advanced_expenses', 'tenant_id')
    op.drop_column('customs_taxes', 'tenant_id')
