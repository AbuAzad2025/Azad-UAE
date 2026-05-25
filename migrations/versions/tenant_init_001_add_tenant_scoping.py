"""add_tenant_scoping

Revision ID: tenant_init_001
Revises: 9f3c1a2b7d4e
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'tenant_init_001'
down_revision = '9f3c1a2b7d4e'
branch_labels = None
depends_on = None


def _ensure_default_tenant(conn):
    row = conn.execute(sa.text("SELECT id FROM tenants WHERE is_active = TRUE ORDER BY id ASC LIMIT 1")).fetchone()
    if row and row[0]:
        return int(row[0])

    conn.execute(
        sa.text(
            "INSERT INTO tenants (name, name_ar, slug, business_type, is_active, created_at) "
            "VALUES (:name, :name_ar, :slug, :business_type, TRUE, CURRENT_TIMESTAMP)"
        ),
        {
            "name": "Default System",
            "name_ar": "النظام الافتراضي",
            "slug": "default",
            "business_type": "general",
        },
    )
    row2 = conn.execute(sa.text("SELECT id FROM tenants WHERE is_active = TRUE ORDER BY id ASC LIMIT 1")).fetchone()
    return int(row2[0])


def _add_tenant_fk(table_name: str, tenant_id: int):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c.get("name") for c in inspector.get_columns(table_name)}

    if "tenant_id" not in existing_cols:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f(f'ix_{table_name}_tenant_id'), ['tenant_id'], unique=False)
            batch_op.create_foreign_key(f'fk_{table_name}_tenant_id', 'tenants', ['tenant_id'], ['id'])

    op.execute(sa.text(f"UPDATE {table_name} SET tenant_id = :tenant_id WHERE tenant_id IS NULL").bindparams(tenant_id=tenant_id))


def upgrade():
    conn = op.get_bind()
    tenant_id = _ensure_default_tenant(conn)

    for t in (
        'branches',
        'users',
        'warehouses',
        'customers',
        'suppliers',
        'product_categories',
        'products',
        'product_partners',
        'purchases',
        'purchase_lines',
        'sales',
        'sale_lines',
        'payments',
        'receipts',
        'cheques',
        'expenses',
        'expense_categories',
        'gl_accounts',
        'gl_journal_entries',
        'gl_journal_lines',
        'product_returns',
        'product_return_lines',
        'employees',
        'salary_advances',
        'payroll_transactions',
        'stock_movements',
    ):
        _add_tenant_fk(t, tenant_id)

    op.create_table(
        'partner_commission_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('sale_line_id', sa.Integer(), nullable=True),
        sa.Column('partner_customer_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('percentage', sa.Numeric(5, 2), nullable=False),
        sa.Column('base_amount_aed', sa.Numeric(15, 3), nullable=False),
        sa.Column('commission_amount_aed', sa.Numeric(15, 3), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id']),
        sa.ForeignKeyConstraint(['sale_line_id'], ['sale_lines.id']),
        sa.ForeignKeyConstraint(['partner_customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_partner_commission_entries_tenant_id', 'partner_commission_entries', ['tenant_id'], unique=False)
    op.create_index('ix_partner_commission_entries_partner_customer_id', 'partner_commission_entries', ['partner_customer_id'], unique=False)
    op.create_index('ix_partner_commission_entries_sale_id', 'partner_commission_entries', ['sale_id'], unique=False)
    op.create_index('ix_partner_commission_entries_branch_id', 'partner_commission_entries', ['branch_id'], unique=False)


def downgrade():
    op.drop_index('ix_partner_commission_entries_branch_id', table_name='partner_commission_entries')
    op.drop_index('ix_partner_commission_entries_sale_id', table_name='partner_commission_entries')
    op.drop_index('ix_partner_commission_entries_partner_customer_id', table_name='partner_commission_entries')
    op.drop_index('ix_partner_commission_entries_tenant_id', table_name='partner_commission_entries')
    op.drop_table('partner_commission_entries')

    for t in (
        'stock_movements',
        'payroll_transactions',
        'salary_advances',
        'employees',
        'product_return_lines',
        'product_returns',
        'gl_journal_lines',
        'gl_journal_entries',
        'gl_accounts',
        'expense_categories',
        'expenses',
        'cheques',
        'receipts',
        'payments',
        'sale_lines',
        'sales',
        'purchase_lines',
        'purchases',
        'product_partners',
        'products',
        'product_categories',
        'suppliers',
        'customers',
        'warehouses',
        'users',
        'branches',
    ):
        with op.batch_alter_table(t, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{t}_tenant_id', type_='foreignkey')
            batch_op.drop_index(batch_op.f(f'ix_{t}_tenant_id'))
            batch_op.drop_column('tenant_id')
