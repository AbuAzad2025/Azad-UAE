"""store_init_005 — SEO, logo, coupons, notifications, gateway ref

Revision ID: store_init_005
Revises: store_init_004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'store_init_005'
down_revision = 'store_init_004'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if 'tenant_stores' in tables:
        cols = {c.get('name') for c in insp.get_columns('tenant_stores')}
        with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
            for name, col in (
                ('logo_path', sa.Column('logo_path', sa.String(255), nullable=True)),
                ('meta_title', sa.Column('meta_title', sa.String(200), nullable=True)),
                ('meta_description', sa.Column('meta_description', sa.String(500), nullable=True)),
                ('meta_keywords', sa.Column('meta_keywords', sa.String(500), nullable=True)),
                ('meta_title_en', sa.Column('meta_title_en', sa.String(200), nullable=True)),
                ('meta_description_en', sa.Column('meta_description_en', sa.String(500), nullable=True)),
                ('return_policy_ar', sa.Column('return_policy_ar', sa.Text(), nullable=True)),
                ('return_policy_en', sa.Column('return_policy_en', sa.Text(), nullable=True)),
                ('low_stock_threshold', sa.Column('low_stock_threshold', sa.Numeric(15, 3), nullable=True, server_default='5')),
                ('notify_whatsapp_on_order', sa.Column('notify_whatsapp_on_order', sa.Boolean(), nullable=False, server_default=sa.text('true'))),
                ('notify_email_on_order', sa.Column('notify_email_on_order', sa.Boolean(), nullable=False, server_default=sa.text('true'))),
                ('subdomain', sa.Column('subdomain', sa.String(100), nullable=True)),
                ('custom_domain', sa.Column('custom_domain', sa.String(255), nullable=True)),
            ):
                if name not in cols:
                    batch_op.add_column(col)

        ts_indexes = {idx.get('name') for idx in insp.get_indexes('tenant_stores')}
        if 'ix_tenant_stores_subdomain' not in ts_indexes:
            op.create_index('ix_tenant_stores_subdomain', 'tenant_stores', ['subdomain'], unique=True)
        if 'ix_tenant_stores_custom_domain' not in ts_indexes:
            op.create_index('ix_tenant_stores_custom_domain', 'tenant_stores', ['custom_domain'], unique=True)

    if 'shop_customer_accounts' in tables:
        cols = {c.get('name') for c in insp.get_columns('shop_customer_accounts')}
        with op.batch_alter_table('shop_customer_accounts', schema=None) as batch_op:
            if 'password_reset_token' not in cols:
                batch_op.add_column(sa.Column('password_reset_token', sa.String(128), nullable=True))
            if 'password_reset_expires_at' not in cols:
                batch_op.add_column(sa.Column('password_reset_expires_at', sa.DateTime(), nullable=True))
        sc_indexes = {idx.get('name') for idx in insp.get_indexes('shop_customer_accounts')}
        if 'ix_shop_customer_password_reset_token' not in sc_indexes:
            op.create_index(
                'ix_shop_customer_password_reset_token',
                'shop_customer_accounts',
                ['password_reset_token'],
                unique=False,
            )

    if 'store_coupons' not in tables:
        op.create_table(
            'store_coupons',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(50), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('discount_percent', sa.Numeric(5, 2), nullable=True),
            sa.Column('discount_amount', sa.Numeric(15, 3), nullable=True),
            sa.Column('min_order_amount', sa.Numeric(15, 3), nullable=True),
            sa.Column('max_uses', sa.Integer(), nullable=True),
            sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('valid_from', sa.DateTime(), nullable=True),
            sa.Column('valid_until', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tenant_id', 'code', name='uq_store_coupon_tenant_code'),
        )
        op.create_index('ix_store_coupons_tenant_id', 'store_coupons', ['tenant_id'], unique=False)
        op.create_index('ix_store_coupons_code', 'store_coupons', ['code'], unique=False)

    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    with op.batch_alter_table('sales', schema=None) as batch_op:
        if 'checkout_gateway_ref' not in sale_cols:
            batch_op.add_column(sa.Column('checkout_gateway_ref', sa.String(120), nullable=True))
        if 'coupon_code' not in sale_cols:
            batch_op.add_column(sa.Column('coupon_code', sa.String(50), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    with op.batch_alter_table('sales', schema=None) as batch_op:
        if 'coupon_code' in sale_cols:
            batch_op.drop_column('coupon_code')
        if 'checkout_gateway_ref' in sale_cols:
            batch_op.drop_column('checkout_gateway_ref')

    if 'store_coupons' in tables:
        op.drop_table('store_coupons')

    if 'shop_customer_accounts' in tables:
        sc_indexes = {idx.get('name') for idx in insp.get_indexes('shop_customer_accounts')}
        if 'ix_shop_customer_password_reset_token' in sc_indexes:
            op.drop_index('ix_shop_customer_password_reset_token', table_name='shop_customer_accounts')
        cols = {c.get('name') for c in insp.get_columns('shop_customer_accounts')}
        with op.batch_alter_table('shop_customer_accounts', schema=None) as batch_op:
            if 'password_reset_expires_at' in cols:
                batch_op.drop_column('password_reset_expires_at')
            if 'password_reset_token' in cols:
                batch_op.drop_column('password_reset_token')

    if 'tenant_stores' in tables:
        ts_indexes = {idx.get('name') for idx in insp.get_indexes('tenant_stores')}
        for idx in ('ix_tenant_stores_custom_domain', 'ix_tenant_stores_subdomain'):
            if idx in ts_indexes:
                op.drop_index(idx, table_name='tenant_stores')
        cols = {c.get('name') for c in insp.get_columns('tenant_stores')}
        with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
            for name in (
                'custom_domain', 'subdomain', 'notify_email_on_order', 'notify_whatsapp_on_order',
                'low_stock_threshold', 'return_policy_en', 'return_policy_ar',
                'meta_description_en', 'meta_title_en', 'meta_keywords', 'meta_description',
                'meta_title', 'logo_path',
            ):
                if name in cols:
                    batch_op.drop_column(name)
