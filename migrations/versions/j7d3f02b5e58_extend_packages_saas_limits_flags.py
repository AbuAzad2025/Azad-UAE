"""extend packages with full SaaS limits and feature flags

Adds the missing quantitative limits (products/customers/suppliers/
warehouses/storage/monthly sales+invoices, -1 = unlimited), the 8
feature flags copied onto tenants at activation, and tier_level used
by utils.pos_features to resolve plan hierarchy from the DB instead of
hardcoded levels.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "j7d3f02b5e58"
down_revision = "i6c2e91a3d47"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("packages") as batch:
        batch.add_column(sa.Column("tier_level", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_products", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_customers", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_suppliers", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_warehouses", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_storage_mb", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_invoices_per_month", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_sales_per_month", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("enable_payroll", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_expenses", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_cheques", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_reports", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_ai", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_store", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_gl", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("enable_api", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("packages") as batch:
        for col in (
            "tier_level",
            "max_products",
            "max_customers",
            "max_suppliers",
            "max_warehouses",
            "max_storage_mb",
            "max_invoices_per_month",
            "max_sales_per_month",
            "enable_payroll",
            "enable_expenses",
            "enable_cheques",
            "enable_reports",
            "enable_ai",
            "enable_store",
            "enable_gl",
            "enable_api",
        ):
            batch.drop_column(col)
