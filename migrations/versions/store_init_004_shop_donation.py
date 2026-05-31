"""store_init_004 — shop customers, donation vault control, donation GL

Revision ID: store_init_004
Revises: store_init_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'store_init_004'
down_revision = 'store_init_003'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if 'shop_customer_accounts' not in tables:
        op.create_table(
            'shop_customer_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=False),
            sa.Column('phone', sa.String(length=30), nullable=True),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('address', sa.Text(), nullable=True),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tenant_id', 'email', name='uq_shop_customer_tenant_email'),
        )
        op.create_index('ix_shop_customer_accounts_tenant_id', 'shop_customer_accounts', ['tenant_id'])
        op.create_index('ix_shop_customer_accounts_email', 'shop_customer_accounts', ['email'])

    if 'payment_vault' in tables:
        pv_cols = {c.get('name') for c in insp.get_columns('payment_vault')}
        with op.batch_alter_table('payment_vault', schema=None) as batch_op:
            if 'donations_enabled' not in pv_cols:
                batch_op.add_column(sa.Column('donations_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=True))
            if 'donation_page_enabled' not in pv_cols:
                batch_op.add_column(sa.Column('donation_page_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=True))
            if 'donation_title_ar' not in pv_cols:
                batch_op.add_column(sa.Column('donation_title_ar', sa.String(length=200), nullable=True))
            if 'donation_title_en' not in pv_cols:
                batch_op.add_column(sa.Column('donation_title_en', sa.String(length=200), nullable=True))
            if 'donation_intro_ar' not in pv_cols:
                batch_op.add_column(sa.Column('donation_intro_ar', sa.Text(), nullable=True))
            if 'donation_intro_en' not in pv_cols:
                batch_op.add_column(sa.Column('donation_intro_en', sa.Text(), nullable=True))
            if 'donation_debit_account' not in pv_cols:
                batch_op.add_column(sa.Column('donation_debit_account', sa.String(length=20), server_default='1120', nullable=True))
            if 'donation_credit_account' not in pv_cols:
                batch_op.add_column(sa.Column('donation_credit_account', sa.String(length=20), server_default='4200', nullable=True))

    if 'donations' in tables:
        d_cols = {c.get('name') for c in insp.get_columns('donations')}
        with op.batch_alter_table('donations', schema=None) as batch_op:
            if 'gl_posted' not in d_cols:
                batch_op.add_column(sa.Column('gl_posted', sa.Boolean(), server_default=sa.text('false'), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if 'donations' in insp.get_table_names():
        cols = {c.get('name') for c in insp.get_columns('donations')}
        if 'gl_posted' in cols:
            with op.batch_alter_table('donations', schema=None) as batch_op:
                batch_op.drop_column('gl_posted')
    if 'payment_vault' in insp.get_table_names():
        cols = {c.get('name') for c in insp.get_columns('payment_vault')}
        with op.batch_alter_table('payment_vault', schema=None) as batch_op:
            for col in ('donation_credit_account', 'donation_debit_account', 'donation_intro_en',
                        'donation_intro_ar', 'donation_title_en', 'donation_title_ar',
                        'donation_page_enabled', 'donations_enabled'):
                if col in cols:
                    batch_op.drop_column(col)
    if 'shop_customer_accounts' in insp.get_table_names():
        op.drop_table('shop_customer_accounts')
