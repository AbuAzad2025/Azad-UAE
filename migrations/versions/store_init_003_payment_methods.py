"""store_init_003 — platform store payment methods

Revision ID: store_init_003
Revises: store_init_002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'store_init_003'
down_revision = 'store_init_002'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if 'store_payment_methods' not in tables:
        op.create_table(
            'store_payment_methods',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('name_ar', sa.String(length=120), nullable=False),
            sa.Column('name_en', sa.String(length=120), nullable=False),
            sa.Column('description_ar', sa.Text(), nullable=True),
            sa.Column('description_en', sa.Text(), nullable=True),
            sa.Column('icon', sa.String(length=80), nullable=True),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('config_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code'),
        )
        op.create_index('ix_store_payment_methods_code', 'store_payment_methods', ['code'], unique=True)
        op.create_index('ix_store_payment_methods_is_enabled', 'store_payment_methods', ['is_enabled'], unique=False)

    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    if 'checkout_payment_method' not in sale_cols:
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.add_column(sa.Column('checkout_payment_method', sa.String(length=50), nullable=True))
        op.create_index('ix_sales_checkout_payment_method', 'sales', ['checkout_payment_method'], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    if 'checkout_payment_method' in sale_cols:
        op.drop_index('ix_sales_checkout_payment_method', table_name='sales')
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.drop_column('checkout_payment_method')
    if 'store_payment_methods' in insp.get_table_names():
        op.drop_table('store_payment_methods')
