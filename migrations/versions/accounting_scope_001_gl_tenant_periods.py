"""Accounting scope: per-tenant COA, GL periods, tenant VAT fields

Revision ID: accounting_scope_001
Revises: tenant_scope_002
"""
from alembic import op
import sqlalchemy as sa


revision = 'accounting_scope_001'
down_revision = 'tenant_scope_002'
branch_labels = None
depends_on = None


def _default_tenant_id(conn):
    row = conn.execute(sa.text("SELECT id FROM tenants WHERE is_active = TRUE ORDER BY id ASC LIMIT 1")).fetchone()
    return int(row[0]) if row and row[0] else None


def upgrade():
    conn = op.get_bind()
    tenant_id = _default_tenant_id(conn)
    inspector = sa.inspect(conn)

    tenant_cols = {c.get('name') for c in inspector.get_columns('tenants')}
    if 'vat_country' not in tenant_cols:
        with op.batch_alter_table('tenants', schema=None) as batch_op:
            batch_op.add_column(sa.Column('vat_country', sa.String(length=2), nullable=True, server_default='AE'))
            batch_op.add_column(sa.Column('vat_number', sa.String(length=100), nullable=True))

    if 'gl_periods' not in inspector.get_table_names():
        op.create_table(
            'gl_periods',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('month', sa.Integer(), nullable=False),
            sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('closed_by', sa.Integer(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tenant_id', 'year', 'month', name='uq_gl_periods_tenant_ym'),
        )
        op.create_index('ix_gl_periods_tenant_id', 'gl_periods', ['tenant_id'], unique=False)

    if tenant_id is not None:
        op.execute(sa.text("UPDATE gl_accounts SET tenant_id = :tid WHERE tenant_id IS NULL").bindparams(tid=tenant_id))
        op.execute(sa.text("UPDATE gl_journal_entries SET tenant_id = :tid WHERE tenant_id IS NULL").bindparams(tid=tenant_id))
        op.execute(sa.text("UPDATE gl_journal_lines SET tenant_id = :tid WHERE tenant_id IS NULL").bindparams(tid=tenant_id))

    gl_indexes = {idx.get('name') for idx in inspector.get_indexes('gl_accounts')}
    if 'ix_gl_accounts_code' in gl_indexes or any('code' in (idx.get('name') or '') for idx in inspector.get_indexes('gl_accounts')):
        try:
            with op.batch_alter_table('gl_accounts', schema=None) as batch_op:
                batch_op.drop_index('ix_gl_accounts_code')
        except Exception:
            pass
    try:
        with op.batch_alter_table('gl_accounts', schema=None) as batch_op:
            batch_op.create_index('ix_gl_accounts_code', ['code'], unique=False)
            batch_op.create_unique_constraint('uq_gl_accounts_tenant_code', ['tenant_id', 'code'])
    except Exception:
        pass

    je_indexes = {idx.get('name') for idx in inspector.get_indexes('gl_journal_entries')}
    try:
        with op.batch_alter_table('gl_journal_entries', schema=None) as batch_op:
            if 'ix_gl_journal_entries_entry_number' in je_indexes:
                batch_op.drop_index('ix_gl_journal_entries_entry_number')
            batch_op.create_index('ix_gl_journal_entries_entry_number', ['entry_number'], unique=False)
            batch_op.create_unique_constraint('uq_gl_journal_entries_tenant_number', ['tenant_id', 'entry_number'])
    except Exception:
        pass


def downgrade():
    op.drop_index('ix_gl_periods_tenant_id', table_name='gl_periods')
    op.drop_table('gl_periods')
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('vat_number')
        batch_op.drop_column('vat_country')
