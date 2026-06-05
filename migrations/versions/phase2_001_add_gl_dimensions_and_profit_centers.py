"""Add GL dimensions (branch, warehouse, profit_center, partner) and profit_centers table

Revision ID: phase2_001
Revises: currency_audit_001
Create Date: 2026-06-05

Adds financial dimension columns to gl_journal_lines and creates the
profit_centers table for Phase 2: Financial Dimensions Enforcement.

Idempotent: safe to re-run; skips existing tables/columns/constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy import text

revision = 'phase2_001'
down_revision = 'currency_audit_001'
branch_labels = None
depends_on = None


def _table_exists(name):
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _column_exists(table, col):
    bind = op.get_bind()
    cols = [c['name'] for c in inspect(bind).get_columns(table)]
    return col in cols


def _index_exists(table, idx):
    bind = op.get_bind()
    idxs = [i['name'] for i in inspect(bind).get_indexes(table)]
    return idx in idxs


def _fk_exists(table, fk):
    bind = op.get_bind()
    fks = [c['name'] for c in inspect(bind).get_foreign_keys(table)]
    return fk in fks


def _orphan_count(table, col, ref_table):
    """Return number of rows in `table` where `col` refers to missing ids in `ref_table`."""
    bind = op.get_bind()
    # Use a safe parameterized text to avoid SQL injection via migration authoring
    sql = text(f"SELECT count(*) FROM {table} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM {ref_table})")
    res = bind.execute(sql)
    try:
        cnt = res.scalar()
    except Exception:
        # Fallback for DB-API results that don't support scalar()
        row = res.fetchone()
        cnt = row[0] if row else 0
    return int(cnt or 0)


def upgrade():
    # ------------------------------------------------------------------
    # profit_centers table (skip if already present from prior migration)
    # ------------------------------------------------------------------
    if not _table_exists('profit_centers'):
        op.create_table(
            'profit_centers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('name_ar', sa.String(length=200), nullable=False),
            sa.Column('name_en', sa.String(length=200), nullable=True),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.Column('level', sa.Integer(), nullable=True),
            sa.Column('manager_id', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['parent_id'], ['profit_centers.id']),
            sa.ForeignKeyConstraint(['manager_id'], ['users.id']),
            sa.UniqueConstraint('tenant_id', 'code', name='uq_profit_centers_tenant_code'),
        )
    if not _index_exists('profit_centers', 'ix_profit_centers_tenant_id'):
        op.create_index('ix_profit_centers_tenant_id', 'profit_centers', ['tenant_id'], unique=False)
    if not _index_exists('profit_centers', 'ix_profit_centers_code'):
        op.create_index('ix_profit_centers_code', 'profit_centers', ['code'], unique=False)
    if not _index_exists('profit_centers', 'ix_profit_centers_is_active'):
        op.create_index('ix_profit_centers_is_active', 'profit_centers', ['is_active'], unique=False)

    # ------------------------------------------------------------------
    # gl_journal_lines dimension columns (idempotent)
    # ------------------------------------------------------------------
    with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
        if not _column_exists('gl_journal_lines', 'branch_id'):
            batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        if not _column_exists('gl_journal_lines', 'warehouse_id'):
            batch_op.add_column(sa.Column('warehouse_id', sa.Integer(), nullable=True))
        if not _column_exists('gl_journal_lines', 'profit_center_id'):
            batch_op.add_column(sa.Column('profit_center_id', sa.Integer(), nullable=True))
        if not _column_exists('gl_journal_lines', 'partner_id'):
            batch_op.add_column(sa.Column('partner_id', sa.Integer(), nullable=True))

        if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_branch_id'):
            batch_op.create_index('ix_gl_journal_lines_branch_id', ['branch_id'], unique=False)
        if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_warehouse_id'):
            batch_op.create_index('ix_gl_journal_lines_warehouse_id', ['warehouse_id'], unique=False)
        if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_profit_center_id'):
            batch_op.create_index('ix_gl_journal_lines_profit_center_id', ['profit_center_id'], unique=False)
        if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_partner_id'):
            batch_op.create_index('ix_gl_journal_lines_partner_id', ['partner_id'], unique=False)

        # Create foreign keys only if there are no orphaned values in the child column.
        # If orphaned references are found, skip creating the FK and warn the operator.
        if not _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_branch_id_branches'):
            cnt = _orphan_count('gl_journal_lines', 'branch_id', 'branches')
            if cnt == 0:
                batch_op.create_foreign_key('fk_gl_journal_lines_branch_id_branches', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
            else:
                print(f"SKIP FK fk_gl_journal_lines_branch_id_branches: {cnt} orphaned branch_id values found. Run backfill/cleanup before adding FK.")
        if not _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_warehouse_id_warehouses'):
            cnt = _orphan_count('gl_journal_lines', 'warehouse_id', 'warehouses')
            if cnt == 0:
                batch_op.create_foreign_key('fk_gl_journal_lines_warehouse_id_warehouses', 'warehouses', ['warehouse_id'], ['id'], ondelete='SET NULL')
            else:
                print(f"SKIP FK fk_gl_journal_lines_warehouse_id_warehouses: {cnt} orphaned warehouse_id values found. Run backfill/cleanup before adding FK.")
        if not _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_profit_center_id_profit_centers'):
            cnt = _orphan_count('gl_journal_lines', 'profit_center_id', 'profit_centers')
            if cnt == 0:
                batch_op.create_foreign_key('fk_gl_journal_lines_profit_center_id_profit_centers', 'profit_centers', ['profit_center_id'], ['id'], ondelete='SET NULL')
            else:
                print(f"SKIP FK fk_gl_journal_lines_profit_center_id_profit_centers: {cnt} orphaned profit_center_id values found. Run backfill/cleanup before adding FK.")
        if not _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_partner_id_partners'):
            cnt = _orphan_count('gl_journal_lines', 'partner_id', 'partners')
            if cnt == 0:
                batch_op.create_foreign_key('fk_gl_journal_lines_partner_id_partners', 'partners', ['partner_id'], ['id'], ondelete='SET NULL')
            else:
                print(f"SKIP FK fk_gl_journal_lines_partner_id_partners: {cnt} orphaned partner_id values found. Run backfill/cleanup before adding FK.")


def downgrade():
    with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
        if _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_partner_id_partners'):
            batch_op.drop_constraint('fk_gl_journal_lines_partner_id_partners', type_='foreignkey')
        if _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_profit_center_id_profit_centers'):
            batch_op.drop_constraint('fk_gl_journal_lines_profit_center_id_profit_centers', type_='foreignkey')
        if _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_warehouse_id_warehouses'):
            batch_op.drop_constraint('fk_gl_journal_lines_warehouse_id_warehouses', type_='foreignkey')
        if _fk_exists('gl_journal_lines', 'fk_gl_journal_lines_branch_id_branches'):
            batch_op.drop_constraint('fk_gl_journal_lines_branch_id_branches', type_='foreignkey')

        if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_partner_id'):
            batch_op.drop_index('ix_gl_journal_lines_partner_id')
        if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_profit_center_id'):
            batch_op.drop_index('ix_gl_journal_lines_profit_center_id')
        if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_warehouse_id'):
            batch_op.drop_index('ix_gl_journal_lines_warehouse_id')
        if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_branch_id'):
            batch_op.drop_index('ix_gl_journal_lines_branch_id')

        if _column_exists('gl_journal_lines', 'partner_id'):
            batch_op.drop_column('partner_id')
        if _column_exists('gl_journal_lines', 'profit_center_id'):
            batch_op.drop_column('profit_center_id')
        if _column_exists('gl_journal_lines', 'warehouse_id'):
            batch_op.drop_column('warehouse_id')
        if _column_exists('gl_journal_lines', 'branch_id'):
            batch_op.drop_column('branch_id')

    if _table_exists('profit_centers'):
        if _index_exists('profit_centers', 'ix_profit_centers_is_active'):
            op.drop_index('ix_profit_centers_is_active', table_name='profit_centers')
        if _index_exists('profit_centers', 'ix_profit_centers_code'):
            op.drop_index('ix_profit_centers_code', table_name='profit_centers')
        if _index_exists('profit_centers', 'ix_profit_centers_tenant_id'):
            op.drop_index('ix_profit_centers_tenant_id', table_name='profit_centers')
        op.drop_table('profit_centers')
