"""add_reconciliation_views

Revision ID: 552bcde29049
Revises: fd3c5d0bb42e
Create Date: 2026-08-21 01:09:27.604703

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '552bcde29049'
down_revision = 'fd3c5d0bb42e'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade():
    # Reconciliation views are advisory-only and portable across PostgreSQL/SQLite.
    # They expose drift between stored aggregates and computed transaction totals.

    if _table_exists("products") and _table_exists("product_warehouse_stock"):
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE VIEW v_product_stock_reconciliation AS
                SELECT
                    p.id,
                    p.tenant_id,
                    p.current_stock AS stored_stock,
                    COALESCE(SUM(pws.quantity), 0) AS computed_stock,
                    p.current_stock - COALESCE(SUM(pws.quantity), 0) AS diff
                FROM products p
                LEFT JOIN product_warehouse_stock pws ON pws.product_id = p.id
                GROUP BY p.id, p.tenant_id, p.current_stock;
                """
            )
        )

    if (
        _table_exists("customers")
        and _table_exists("sales")
        and _table_exists("receipts")
        and _table_exists("product_returns")
    ):
        # Build filters dynamically because not all tables have is_active.
        sales_filter = "WHERE is_active = true" if _has_column("sales", "is_active") else ""
        receipts_filter = "WHERE is_active = true" if _has_column("receipts", "is_active") else ""

        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE VIEW v_customer_balance_reconciliation AS
                SELECT
                    c.id,
                    c.tenant_id,
                    c.balance AS stored_balance,
                    COALESCE(r.total_receipts, 0)
                        + COALESCE(ret.total_returns, 0)
                        - COALESCE(s.total_sales, 0) AS computed_balance,
                    c.balance
                        - (COALESCE(r.total_receipts, 0)
                           + COALESCE(ret.total_returns, 0)
                           - COALESCE(s.total_sales, 0)) AS diff
                FROM customers c
                LEFT JOIN (
                    SELECT customer_id, SUM(amount_aed) AS total_sales
                    FROM sales
                    {sales_filter}
                    GROUP BY customer_id
                ) s ON s.customer_id = c.id
                LEFT JOIN (
                    SELECT customer_id, SUM(amount_aed) AS total_receipts
                    FROM receipts
                    {receipts_filter}
                    GROUP BY customer_id
                ) r ON r.customer_id = c.id
                LEFT JOIN (
                    SELECT customer_id, SUM(amount_aed) AS total_returns
                    FROM product_returns
                    WHERE status IN ('approved', 'completed')
                    GROUP BY customer_id
                ) ret ON ret.customer_id = c.id;
                """
            )
        )


def downgrade():
    if _table_exists("v_product_stock_reconciliation"):
        op.execute(sa.text("DROP VIEW IF EXISTS v_product_stock_reconciliation;"))
    if _table_exists("v_customer_balance_reconciliation"):
        op.execute(sa.text("DROP VIEW IF EXISTS v_customer_balance_reconciliation;"))
