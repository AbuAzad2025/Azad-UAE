"""Add missing customers.country column

Revision ID: add_missing_customers_country_001
Revises: print_system_001_add_print_history
Create Date: 2026-06-13 01:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_missing_customers_country_001'
down_revision = 'print_system_001_add_print_history'
branch_labels = None
depends_on = None


def upgrade():
    # IDEMPOTENT PATCH: Add customers.country only if missing
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('customers')]
    
    if 'country' not in columns:
        with op.batch_alter_table('customers', schema=None) as batch_op:
            batch_op.add_column(sa.Column('country', sa.String(length=2), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("customers")]
    if "country" in columns:
        with op.batch_alter_table("customers", schema=None) as batch_op:
            batch_op.drop_column("country")
