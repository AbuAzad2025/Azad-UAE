"""production_schema_hardening_round1

Revision ID: prod_schema_hardening_001
Revises: normalize_legacy_round1_001
Create Date: 2026-06-01 16:00:00.000000

Per-tenant business unique keys, tenant_id NOT NULL on operational tables,
GL historical line rounding fix, and safe CHECK constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "prod_schema_hardening_001"
down_revision = "normalize_legacy_round1_001"
branch_labels = None
depends_on = None

KNOWN_GL_LINE_IDS = (721, 995, 1405)

TENANT_NOT_NULL_TABLES = [
    "branches", "products", "product_categories", "product_partners",
    "customers", "suppliers", "sales", "sale_lines", "purchases", "purchase_lines",
    "payments", "expenses", "warehouses", "stock_movements",
    "gl_accounts", "gl_journal_entries", "gl_journal_lines",
    "partner_commission_entries", "employees", "salary_advances", "payroll_transactions",
    "tenant_stores", "shop_customer_accounts", "store_coupons", "invoice_settings",
]

# Global unique indexes/constraints to drop (safe IF EXISTS)
GLOBAL_INDEXES_TO_DROP = [
    "ix_products_sku",
    "ix_products_barcode",
    "ix_product_categories_name",
    "branches_name_key",
    "branches_code_key",
    "warehouses_name_key",
    "warehouses_code_key",
    "ix_sales_sale_number",
    "ix_purchases_purchase_number",
    "ix_payments_payment_number",
    "ix_cheques_cheque_number",
]

GLOBAL_CONSTRAINTS_TO_DROP = [
    ("branches", "branches_name_key"),
    ("branches", "branches_code_key"),
    ("warehouses", "warehouses_name_key"),
    ("warehouses", "warehouses_code_key"),
]

PER_TENANT_UNIQUE_INDEXES = [
    (
        "uq_products_tenant_sku",
        "products",
        "CREATE UNIQUE INDEX uq_products_tenant_sku ON products (tenant_id, sku) "
        "WHERE sku IS NOT NULL AND TRIM(sku) <> ''",
    ),
    (
        "uq_products_tenant_barcode",
        "products",
        "CREATE UNIQUE INDEX uq_products_tenant_barcode ON products (tenant_id, barcode) "
        "WHERE barcode IS NOT NULL AND TRIM(barcode) <> ''",
    ),
    (
        "uq_product_categories_tenant_name",
        "product_categories",
        "CREATE UNIQUE INDEX uq_product_categories_tenant_name "
        "ON product_categories (tenant_id, name)",
    ),
    (
        "uq_branches_tenant_name",
        "branches",
        "CREATE UNIQUE INDEX uq_branches_tenant_name ON branches (tenant_id, name)",
    ),
    (
        "uq_branches_tenant_code",
        "branches",
        "CREATE UNIQUE INDEX uq_branches_tenant_code ON branches (tenant_id, code)",
    ),
    (
        "uq_warehouses_tenant_name",
        "warehouses",
        "CREATE UNIQUE INDEX uq_warehouses_tenant_name ON warehouses (tenant_id, name)",
    ),
    (
        "uq_warehouses_tenant_code",
        "warehouses",
        "CREATE UNIQUE INDEX uq_warehouses_tenant_code ON warehouses (tenant_id, code)",
    ),
    (
        "uq_sales_tenant_sale_number",
        "sales",
        "CREATE UNIQUE INDEX uq_sales_tenant_sale_number ON sales (tenant_id, sale_number)",
    ),
    (
        "uq_purchases_tenant_purchase_number",
        "purchases",
        "CREATE UNIQUE INDEX uq_purchases_tenant_purchase_number "
        "ON purchases (tenant_id, purchase_number)",
    ),
    (
        "uq_payments_tenant_payment_number",
        "payments",
        "CREATE UNIQUE INDEX uq_payments_tenant_payment_number "
        "ON payments (tenant_id, payment_number)",
    ),
    (
        "uq_cheques_tenant_cheque_number",
        "cheques",
        "CREATE UNIQUE INDEX uq_cheques_tenant_cheque_number "
        "ON cheques (tenant_id, cheque_number)",
    ),
]

CHECKS_UPGRADE = [
    (
        "ck_gl_journal_lines_single_sided_amount",
        "gl_journal_lines",
        "(debit >= 0 AND credit >= 0) AND "
        "((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))",
    ),
    (
        "ck_invoice_settings_active_requires_tenant",
        "invoice_settings",
        "(is_active = false OR tenant_id IS NOT NULL)",
    ),
    (
        "ck_sales_currency_iso3",
        "sales",
        "(currency IS NULL OR currency ~ '^[A-Z]{3}$')",
    ),
    (
        "ck_payments_currency_iso3",
        "payments",
        "(currency IS NULL OR currency ~ '^[A-Z]{3}$')",
    ),
    (
        "ck_purchases_currency_iso3",
        "purchases",
        "(currency IS NULL OR currency ~ '^[A-Z]{3}$')",
    ),
    (
        "ck_tenants_default_currency_iso3",
        "tenants",
        "(default_currency IS NULL OR default_currency ~ '^[A-Z]{3}$')",
    ),
    (
        "ck_payments_amount_nonneg",
        "payments",
        "(amount IS NULL OR amount >= 0)",
    ),
    (
        "ck_sales_total_amount_nonneg",
        "sales",
        "(total_amount IS NULL OR total_amount >= 0)",
    ),
    (
        "ck_sale_lines_quantity_nonneg",
        "sale_lines",
        "(quantity IS NULL OR quantity >= 0)",
    ),
    (
        "ck_sale_lines_unit_price_nonneg",
        "sale_lines",
        "(unit_price IS NULL OR unit_price >= 0)",
    ),
    (
        "ck_purchase_lines_quantity_nonneg",
        "purchase_lines",
        "(quantity IS NULL OR quantity >= 0)",
    ),
    (
        "ck_purchase_lines_unit_cost_nonneg",
        "purchase_lines",
        "(unit_cost IS NULL OR unit_cost >= 0)",
    ),
]

CHECK_NAMES = [c[0] for c in CHECKS_UPGRADE]
PER_TENANT_INDEX_NAMES = [c[0] for c in PER_TENANT_UNIQUE_INDEXES]


def _table_has_column(conn, table: str, column: str) -> bool:
    insp = inspect(conn)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _assert_tenant_nulls_zero(conn) -> None:
    for table in TENANT_NOT_NULL_TABLES:
        if not _table_has_column(conn, table, "tenant_id"):
            continue
        n = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id IS NULL')
        ).scalar()
        if n:
            raise RuntimeError(f"Precheck failed: {table}.tenant_id has {n} NULL rows")


def _fix_gl_dual_side_lines(conn) -> None:
    ids = ",".join(str(i) for i in KNOWN_GL_LINE_IDS)
    conn.execute(
        sa.text(
            f"""
            UPDATE gl_journal_lines
            SET debit = debit - credit, credit = 0
            WHERE id IN ({ids}) AND debit > credit AND credit > 0
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            UPDATE gl_journal_lines
            SET credit = credit - debit, debit = 0
            WHERE id IN ({ids}) AND credit > debit AND debit > 0
            """
        )
    )
    entry_ids = conn.execute(
        sa.text(
            f"SELECT DISTINCT entry_id FROM gl_journal_lines WHERE id IN ({ids})"
        )
    ).fetchall()
    for (eid,) in entry_ids:
        totals = conn.execute(
            sa.text(
                """
                SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
                FROM gl_journal_lines WHERE entry_id = :eid
                """
            ),
            {"eid": eid},
        ).one()
        conn.execute(
            sa.text(
                """
                UPDATE gl_journal_entries
                SET total_debit = :td, total_credit = :tc
                WHERE id = :eid
                """
            ),
            {"eid": eid, "td": totals[0], "tc": totals[1]},
        )


def upgrade():
    conn = op.get_bind()
    _assert_tenant_nulls_zero(conn)

    dual = conn.execute(
        sa.text(
            "SELECT id FROM gl_journal_lines WHERE debit > 0 AND credit > 0 "
            f"AND id NOT IN ({','.join(str(i) for i in KNOWN_GL_LINE_IDS)})"
        )
    ).fetchall()
    if dual:
        raise RuntimeError(f"Unexpected GL dual-side lines: {[r[0] for r in dual]}")

    _fix_gl_dual_side_lines(conn)

    for table, cname in GLOBAL_CONSTRAINTS_TO_DROP:
        op.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{cname}"'))
    constraint_index_names = {c[1] for c in GLOBAL_CONSTRAINTS_TO_DROP}
    for idx_name in GLOBAL_INDEXES_TO_DROP:
        if idx_name in constraint_index_names:
            continue
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{idx_name}"'))

    for idx_name, _table, ddl in PER_TENANT_UNIQUE_INDEXES:
        op.execute(sa.text(ddl))

    for table in TENANT_NOT_NULL_TABLES:
        if _table_has_column(conn, table, "tenant_id"):
            op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)

    for cname, table, expr in CHECKS_UPGRADE:
        if not inspect(conn).has_table(table):
            continue
        col = expr.split()[0].strip("(") if "(" in expr else None
        if col and col not in {c["name"] for c in inspect(conn).get_columns(table)}:
            continue
        op.create_check_constraint(cname, table, expr)


def downgrade():
    conn = op.get_bind()

    for cname, table, _expr in reversed(CHECKS_UPGRADE):
        if inspect(conn).has_table(table):
            op.drop_constraint(cname, table, type_="check")

    for table in TENANT_NOT_NULL_TABLES:
        if _table_has_column(conn, table, "tenant_id"):
            op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=True)

    for idx_name, _table, _ddl in PER_TENANT_UNIQUE_INDEXES:
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{idx_name}"'))

    # Restore global uniques only where safe (empty DB assumption may not hold — see comments)
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_products_sku ON products (sku)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_products_barcode ON products (barcode)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_product_categories_name ON product_categories (name)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS branches_name_key ON branches (name)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS branches_code_key ON branches (code)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS warehouses_name_key ON warehouses (name)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS warehouses_code_key ON warehouses (code)"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_sale_number ON sales (sale_number)"))
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_purchases_purchase_number "
            "ON purchases (purchase_number)"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_payment_number "
            "ON payments (payment_number)"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_cheques_cheque_number "
            "ON cheques (cheque_number)"
        )
    )
