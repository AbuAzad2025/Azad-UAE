"""Migration for the maintenance module — tables, GL concepts, tenant flag.

Revision ID: m3a4b5c6d7e8
Revises: f4a5b6c7d809
Create Date: 2026-11-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m3a4b5c6d7e8"
down_revision = "f4a5b6c7d809"
branch_labels = None
depends_on = None

_MAINTENANCE_CONCEPTS = frozenset(
    {
        "MAINTENANCE_REVENUE",
        "MAINTENANCE_AR",
        "MAINTENANCE_AP",
        "MAINTENANCE_COGS",
        "MAINTENANCE_CASH_DIFFERENCE",
        "MAINTENANCE_DEPOSIT",
    }
)


def _rebuild_concept_check(*, include_maintenance: bool) -> None:
    from models._constants import GL_CONCEPT_CODES

    codes = [code for code in GL_CONCEPT_CODES if include_maintenance or code not in _MAINTENANCE_CONCEPTS]
    expression = "concept_code IN ({})".format(", ".join(f"'{code}'" for code in codes))
    with op.batch_alter_table("gl_account_mappings") as batch_op:
        batch_op.drop_constraint("ck_gl_account_mappings_concept_code", type_="check")
        batch_op.create_check_constraint("ck_gl_account_mappings_concept_code", expression)


#: The maintenance module's own accounts. They are inserted for every tenant
#: that already has a chart, because the boot provisioner
#: (``GLService.ensure_core_accounts``) only creates the BASE_ACCOUNTS tree and
#: the industry extension - a tenant whose maintenance module was enabled
#: after the base tree was built would otherwise have no account to map the
#: maintenance concepts to, and every maintenance posting would be refused.
_MAINTENANCE_ACCOUNTS = (
    # code, name, name_ar, type, level, parent_code
    ("1134", "AR - Maintenance", "ذمم صيانة", "asset", 3, "1130"),
    ("2171", "Maintenance Customer Deposits", "عربون صيانة", "liability", 3, "2170"),
    ("4119", "Maintenance Revenue", "إيرادات الصيانة", "revenue", 2, "4100"),
    ("5119", "Maintenance Cost of Parts", "تكلفة قطع الصيانة", "expense", 2, "5100"),
    ("6560", "Maintenance Cash Difference", "فروقات صندوق الصيانة", "expense", 1, "6000"),
)


#: The maintenance module writes its own stock movements. The database
#: constraint ``ck_stock_movement_type`` (created by
#: ``86afead128ce_add_integrity_constraints_phase1``) lists the trading
#: movement types only, so PostgreSQL refuses a maintenance movement with a
#: CheckViolation. The constraint is widened here rather than in the
#: revision that created it, which has already run on production.
_STOCK_MOVEMENT_TYPES = "'purchase','sale','adjustment','return','damage','transfer','maintenance','maintenance_return'"


def _widen_stock_movement_type_constraint(*, include_maintenance: bool) -> None:
    if not _table_exists("stock_movements"):
        return
    types = (
        _STOCK_MOVEMENT_TYPES if include_maintenance else "'purchase','sale','adjustment','return','damage','transfer'"
    )
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.drop_constraint("ck_stock_movement_type", type_="check")
        batch_op.create_check_constraint("ck_stock_movement_type", sa.text(f"movement_type IN ({types})"))


def _provision_maintenance_accounts() -> None:
    """Insert the maintenance accounts into every tenant that has a chart."""
    bind = op.get_bind()
    tenant_rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT t.id AS tenant_id, COALESCE(t.default_currency, 'ILS') AS currency
            FROM tenants t
            WHERE EXISTS (SELECT 1 FROM gl_accounts g WHERE g.tenant_id = t.id)
            """
        )
    ).fetchall()
    for tenant_id, currency in tenant_rows:
        for code, name, name_ar, acc_type, level, parent_code in _MAINTENANCE_ACCOUNTS:
            exists = bind.execute(
                sa.text("SELECT 1 FROM gl_accounts WHERE tenant_id = :t AND code = :c LIMIT 1"),
                {"t": tenant_id, "c": code},
            ).first()
            if exists:
                continue
            parent_id = bind.execute(
                sa.text("SELECT id FROM gl_accounts WHERE tenant_id = :t AND code = :p LIMIT 1"),
                {"t": tenant_id, "p": parent_code},
            ).scalar()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO gl_accounts
                        (tenant_id, code, name, name_ar, type, sub_type,
                         is_header, parent_id, is_active, is_contra,
                         liquidity_kind, is_default_liquidity, is_reconcile,
                         currency, level,
                         created_at, updated_at)
                    VALUES
                        (:t, :c, :n, :nar, :ty, :st,
                         false, :pid, true, false,
                         NULL, false, false,
                         :cur, :lvl,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "t": tenant_id,
                    "c": code,
                    "n": name,
                    "nar": name_ar,
                    "ty": acc_type,
                    "st": None,
                    "pid": parent_id,
                    "cur": currency,
                    "lvl": level,
                },
            )


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False


def _add_maintenance_einvoice_link() -> None:
    """Let an e-invoice artifact hang off a maintenance invoice.

    A maintenance job is a sale for the tax authority, so it carries the
    same UBL document - but the artifact must reference the maintenance
    document, not a sale row, or the two ledgers would share one key.
    """
    if not _table_exists("e_invoices"):
        return
    if _column_exists("e_invoices", "maintenance_invoice_id"):
        return
    with op.batch_alter_table("e_invoices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "maintenance_invoice_id",
                sa.Integer(),
                sa.ForeignKey("maintenance_invoices.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_e_invoices_maintenance_invoice_id", ["maintenance_invoice_id"], unique=False)


def _install_warranty_audit_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_maintenance_warranty_audit_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'maintenance warranty audit records are append-only';
            END;
            $$
        """)
        op.execute("DROP TRIGGER IF EXISTS maintenance_warranty_audit_append_only ON maintenance_warranty_audit")
        op.execute("""
            CREATE TRIGGER maintenance_warranty_audit_append_only
            BEFORE UPDATE OR DELETE ON maintenance_warranty_audit
            FOR EACH ROW EXECUTE FUNCTION prevent_maintenance_warranty_audit_change()
        """)
    elif dialect == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER IF NOT EXISTS maintenance_warranty_audit_no_{action.lower()}
                BEFORE {action} ON maintenance_warranty_audit
                BEGIN
                    SELECT RAISE(ABORT, 'maintenance warranty audit records are append-only');
                END
            """)
    else:
        raise RuntimeError(f"Unsupported database for warranty audit protection: {dialect}")


def _install_archive_only_guards() -> None:
    tables = (
        "maintenance_orders",
        "maintenance_order_lines",
        "maintenance_order_services",
        "maintenance_order_status_logs",
        "maintenance_receipts",
        "maintenance_invoices",
        "maintenance_returns",
        "maintenance_return_lines",
        "maintenance_services",
        "maintenance_device_registry",
    )
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_maintenance_record_delete()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'maintenance records are archive-only';
            END;
            $$
        """)
        for table in tables:
            op.execute(f"DROP TRIGGER IF EXISTS maintenance_no_delete ON {table}")
            op.execute(f"""
                CREATE TRIGGER maintenance_no_delete BEFORE DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION prevent_maintenance_record_delete()
            """)
        op.execute("DROP TRIGGER IF EXISTS maintenance_history_no_update ON maintenance_order_status_logs")
        op.execute("""
            CREATE TRIGGER maintenance_history_no_update BEFORE UPDATE ON maintenance_order_status_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_maintenance_record_delete()
        """)
    elif dialect == "sqlite":
        for table in tables:
            op.execute(f"""
                CREATE TRIGGER IF NOT EXISTS no_delete_{table} BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'maintenance records are archive-only');
                END
            """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS maintenance_history_no_update BEFORE UPDATE ON maintenance_order_status_logs
            BEGIN
                SELECT RAISE(ABORT, 'maintenance status history is append-only');
            END
        """)
    else:
        raise RuntimeError(f"Unsupported database for maintenance archive protection: {dialect}")


def upgrade() -> None:
    # Existing installations are already past the earlier allow-list rebuilds.
    _rebuild_concept_check(include_maintenance=True)
    _widen_stock_movement_type_constraint(include_maintenance=True)
    _provision_maintenance_accounts()
    # ── enable_maintenance flag on tenants ──
    if not _column_exists("tenants", "enable_maintenance"):
        with op.batch_alter_table("tenants", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "enable_maintenance",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                )
            )

    # ── maintenance_orders ──
    if not _table_exists("maintenance_orders"):
        op.create_table(
            "maintenance_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("branch_id", sa.Integer(), nullable=True, index=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True, index=True),
            sa.Column("order_number", sa.String(length=50), nullable=False, index=True),
            sa.Column(
                "order_date",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("customer_id", sa.Integer(), nullable=True, index=True),
            sa.Column("customer_name", sa.String(length=200), nullable=True),
            sa.Column("customer_phone", sa.String(length=50), nullable=True),
            sa.Column("device_brand", sa.String(length=100), nullable=True),
            sa.Column("device_model", sa.String(length=100), nullable=True),
            sa.Column("device_serial_number", sa.String(length=100), nullable=True),
            sa.Column("device_imei", sa.String(length=100), nullable=True),
            sa.Column("device_plate", sa.String(length=50), nullable=True),
            sa.Column("device_km", sa.Integer(), nullable=True),
            sa.Column("device_fault_description", sa.Text(), nullable=True),
            sa.Column("subtotal", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_line_total", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_total_percent", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("discount_total_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("tax_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("taxable_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("paid_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("balance_due", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("deposit_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("currency", sa.String(length=3), nullable=False, default="AED"),
            sa.Column("exchange_rate", sa.Numeric(precision=15, scale=6), nullable=False, default=1),
            sa.Column("base_currency", sa.String(length=3), nullable=False, default="AED"),
            sa.Column("amount_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("paid_amount_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("balance_due_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("prices_include_vat", sa.Boolean(), nullable=False, default=False),
            sa.Column("status", sa.String(length=20), nullable=False, default="received", index=True),
            sa.Column("priority", sa.String(length=20), nullable=False, default="normal"),
            sa.Column("warranty_status", sa.String(length=20), nullable=False, default="unknown", index=True),
            sa.Column("warranty_checked", sa.Boolean(), nullable=False, default=False),
            sa.Column("warranty_checked_by", sa.Integer(), nullable=True, index=True),
            sa.Column("warranty_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("warranty_notes", sa.Text(), nullable=True),
            sa.Column("warranty_sale_id", sa.Integer(), nullable=True, index=True),
            sa.Column("color_tag", sa.String(length=7), nullable=False, default="#10b981"),
            sa.Column("received_by", sa.Integer(), nullable=False, index=True),
            sa.Column("engineer_id", sa.Integer(), nullable=True, index=True),
            sa.Column("service_advisor_id", sa.Integer(), nullable=True, index=True),
            sa.Column("closed_by", sa.Integer(), nullable=True, index=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("terms_and_conditions", sa.Text(), nullable=True),
            sa.Column("customer_signature", sa.Boolean(), nullable=False, default=False),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_by", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_orders_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["branch_id"], ["branches.id"], name="fk_maintenance_orders_branch_id_branches", ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="fk_maintenance_orders_warehouse_id_warehouses",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="fk_maintenance_orders_customer_id_customers",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["received_by"], ["users.id"], name="fk_maintenance_orders_received_by_users", ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["engineer_id"], ["users.id"], name="fk_maintenance_orders_engineer_id_users", ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["service_advisor_id"],
                ["users.id"],
                name="fk_maintenance_orders_service_advisor_id_users",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["closed_by"], ["users.id"], name="fk_maintenance_orders_closed_by_users", ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["warranty_checked_by"],
                ["users.id"],
                name="fk_maintenance_orders_warranty_checked_by_users",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["warranty_sale_id"],
                ["sales.id"],
                name="fk_maintenance_orders_warranty_sale_id_sales",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["archived_by"], ["users.id"], name="fk_maintenance_orders_archived_by_users", ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "order_number", name="uq_maintenance_orders_tenant_number"),
        )
        op.create_index("idx_maintenance_orders_tenant_status", "maintenance_orders", ["tenant_id", "status"])
        op.create_index("idx_maintenance_orders_tenant_date", "maintenance_orders", ["tenant_id", "created_at"])
        op.create_index("idx_maintenance_orders_customer", "maintenance_orders", ["tenant_id", "customer_id"])
        op.create_index("idx_maintenance_orders_engineer", "maintenance_orders", ["tenant_id", "engineer_id"])
        op.create_index("idx_maintenance_orders_warranty", "maintenance_orders", ["tenant_id", "warranty_status"])

    # ── maintenance_order_lines ──
    if not _table_exists("maintenance_order_lines"):
        op.create_table(
            "maintenance_order_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("product_id", sa.Integer(), nullable=False, index=True),
            sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False, default=1),
            sa.Column("quantity_returned", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("unit_price", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("discount_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_mode", sa.String(length=20), nullable=False, default="percent"),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("tax_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("warehouse_id", sa.Integer(), nullable=True, index=True),
            sa.Column("movement_id", sa.Integer(), nullable=True, index=True),
            sa.Column("cost_price", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("cost_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("aggregate_discount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("taxable_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_order_lines_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_order_lines_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="fk_maintenance_order_lines_product_id_products",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="fk_maintenance_order_lines_warehouse_id_warehouses",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["movement_id"],
                ["stock_movements.id"],
                name="fk_maintenance_order_lines_movement_id_stock_movements",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "order_id", "product_id", name="uq_maintenance_order_lines_tenant_order_product"
            ),
        )
        op.create_index("idx_maintenance_order_lines_order", "maintenance_order_lines", ["tenant_id", "order_id"])

    # ── maintenance_order_services ──
    if not _table_exists("maintenance_order_services"):
        op.create_table(
            "maintenance_order_services",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("service_code", sa.String(length=50), nullable=False, index=True),
            sa.Column("service_name", sa.String(length=200), nullable=False),
            sa.Column("service_name_ar", sa.String(length=200), nullable=True),
            sa.Column("service_category", sa.String(length=50), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, default=0),
            sa.Column("unit_price", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("discount_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_mode", sa.String(length=20), nullable=False, default="percent"),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("tax_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("engineer_id", sa.Integer(), nullable=True, index=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_order_services_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_order_services_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["engineer_id"],
                ["users.id"],
                name="fk_maintenance_order_services_engineer_id_users",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_maintenance_order_services_order", "maintenance_order_services", ["tenant_id", "order_id"])

    # ── maintenance_order_status_logs ──
    if not _table_exists("maintenance_order_status_logs"):
        op.create_table(
            "maintenance_order_status_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("from_status", sa.String(length=50), nullable=True),
            sa.Column("to_status", sa.String(length=50), nullable=False, index=True),
            sa.Column("changed_by", sa.Integer(), nullable=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_order_status_logs_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_order_status_logs_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["changed_by"],
                ["users.id"],
                name="fk_maintenance_order_status_logs_changed_by_users",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_maintenance_order_status_logs_order", "maintenance_order_status_logs", ["tenant_id", "order_id"]
        )
        op.create_index(
            "idx_maintenance_order_status_logs_created", "maintenance_order_status_logs", ["tenant_id", "created_at"]
        )

    # ── maintenance_receipts ──
    if not _table_exists("maintenance_receipts"):
        op.create_table(
            "maintenance_receipts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("receipt_number", sa.String(length=50), nullable=False, index=True),
            sa.Column(
                "receipt_date",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("payment_mode", sa.String(length=20), nullable=False),
            sa.Column("reference_number", sa.String(length=100), nullable=True),
            sa.Column("cashier_id", sa.Integer(), nullable=False, index=True),
            sa.Column("is_deposit", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column("gl_posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("gl_posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gl_entry_id", sa.Integer(), nullable=True, index=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_receipts_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_receipts_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["cashier_id"], ["users.id"], name="fk_maintenance_receipts_cashier_id_users", ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["gl_entry_id"],
                ["gl_journal_entries.id"],
                name="fk_maintenance_receipts_gl_entry_id_gl_journal_entries",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "receipt_number", name="uq_maintenance_receipts_tenant_number"),
        )

    # ── maintenance_invoices ──
    if not _table_exists("maintenance_invoices"):
        op.create_table(
            "maintenance_invoices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("invoice_number", sa.String(length=50), nullable=False, index=True),
            sa.Column(
                "invoice_date",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("subtotal", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("discount_total_percent", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("discount_total_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("tax_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("taxable_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("paid_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("balance_due", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("currency", sa.String(length=3), nullable=False, default="AED"),
            sa.Column("exchange_rate", sa.Numeric(precision=15, scale=6), nullable=False, default=1),
            sa.Column("base_currency", sa.String(length=3), nullable=False, default="AED"),
            sa.Column("amount_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("paid_amount_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("balance_due_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("prices_include_vat", sa.Boolean(), nullable=False, default=False),
            sa.Column("posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gl_posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("gl_posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gl_entry_id", sa.Integer(), nullable=True, index=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_invoices_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_invoices_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["gl_entry_id"],
                ["gl_journal_entries.id"],
                name="fk_maintenance_invoices_gl_entry_id_gl_journal_entries",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "invoice_number", name="uq_maintenance_invoices_tenant_number"),
            sa.UniqueConstraint("tenant_id", "order_id", name="uq_maintenance_invoices_tenant_order"),
        )

    # ── maintenance_returns ──
    if not _table_exists("maintenance_returns"):
        op.create_table(
            "maintenance_returns",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("return_number", sa.String(length=50), nullable=False, index=True),
            sa.Column(
                "return_date",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("returned_by", sa.Integer(), nullable=False, index=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("total_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_value_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_value_tax", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_value_cost", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gl_posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_returns_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_returns_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["returned_by"], ["users.id"], name="fk_maintenance_returns_returned_by_users", ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "return_number", name="uq_maintenance_returns_tenant_number"),
        )

    # ── maintenance_return_lines ──
    if not _table_exists("maintenance_return_lines"):
        op.create_table(
            "maintenance_return_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("return_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_line_id", sa.Integer(), nullable=True, index=True),
            sa.Column("order_service_id", sa.Integer(), nullable=True, index=True),
            sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False, default=1),
            sa.Column("unit_price", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total_aed", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total_tax", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("unit_cost", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("line_total_cost", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_return_lines_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["return_id"],
                ["maintenance_returns.id"],
                name="fk_maintenance_return_lines_return_id_maintenance_returns",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["order_line_id"],
                ["maintenance_order_lines.id"],
                name="fk_maint_return_line_order_line",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["order_service_id"],
                ["maintenance_order_services.id"],
                name="fk_maint_return_line_order_service",
                ondelete="SET NULL",
            ),
        )
        op.create_index("idx_maintenance_return_lines_return", "maintenance_return_lines", ["tenant_id", "return_id"])

    # ── maintenance_settings ──
    if not _table_exists("maintenance_settings"):
        op.create_table(
            "maintenance_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True, unique=True),
            sa.Column("default_warehouse_id", sa.Integer(), nullable=True, index=True),
            sa.Column("maintenance_ar_account_id", sa.Integer(), nullable=True, index=True),
            sa.Column("maintenance_revenue_account_id", sa.Integer(), nullable=True, index=True),
            sa.Column("maintenance_cogs_account_id", sa.Integer(), nullable=True, index=True),
            sa.Column("max_discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, default=15),
            sa.Column("max_discount_value", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("allow_engineer_discount", sa.Boolean(), nullable=False, default=True),
            sa.Column("require_manager_approval_above_discount", sa.Boolean(), nullable=False, default=True),
            sa.Column("require_warranty_check", sa.Boolean(), nullable=False, default=True),
            sa.Column("color_warranty", sa.String(length=7), nullable=False, default="#10b981"),
            sa.Column("color_non_warranty", sa.String(length=7), nullable=False, default="#ef4444"),
            sa.Column("color_unknown_warranty", sa.String(length=7), nullable=False, default="#f59e0b"),
            sa.Column("allow_engineer_cancel_warranty", sa.Boolean(), nullable=False, default=False),
            sa.Column("allow_engineer_restore_warranty", sa.Boolean(), nullable=False, default=False),
            sa.Column("invoice_prefix", sa.String(length=20), nullable=False, default="MINV"),
            sa.Column("receipt_prefix", sa.String(length=20), nullable=False, default="PT"),
            sa.Column("order_prefix", sa.String(length=20), nullable=False, default="MN"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_settings_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["default_warehouse_id"],
                ["warehouses.id"],
                name="fk_maintenance_settings_default_warehouse_id_warehouses",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["maintenance_ar_account_id"],
                ["gl_accounts.id"],
                name="fk_maintenance_settings_maintenance_ar_account_id_gl_accounts",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["maintenance_revenue_account_id"],
                ["gl_accounts.id"],
                name="fk_maint_settings_revenue_account",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["maintenance_cogs_account_id"],
                ["gl_accounts.id"],
                name="fk_maintenance_settings_maintenance_cogs_account_id_gl_accounts",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    # ── maintenance_services ──
    if not _table_exists("maintenance_services"):
        op.create_table(
            "maintenance_services",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("service_code", sa.String(length=50), nullable=False, index=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("name_ar", sa.String(length=200), nullable=True),
            sa.Column("service_category", sa.String(length=50), nullable=False, index=True),
            sa.Column("fixed_price", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, default=0),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("requires_parts", sa.Boolean(), nullable=False, default=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"], name="fk_maintenance_services_tenant_id_tenants", ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "service_code", name="uq_maintenance_services_tenant_code"),
        )
        op.create_index(
            "idx_maintenance_services_tenant_category", "maintenance_services", ["tenant_id", "service_category"]
        )

    # ── maintenance_device_registry ──
    if not _table_exists("maintenance_device_registry"):
        op.create_table(
            "maintenance_device_registry",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer(), nullable=True, index=True),
            sa.Column("product_id", sa.Integer(), nullable=True, index=True),
            sa.Column("brand", sa.String(length=100), nullable=True),
            sa.Column("model", sa.String(length=100), nullable=True),
            sa.Column("serial_number", sa.String(length=100), nullable=True, index=True),
            sa.Column("imei", sa.String(length=100), nullable=True, index=True),
            sa.Column("plate", sa.String(length=50), nullable=True, index=True),
            sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("warranty_start_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("warranty_end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("warranty_type", sa.String(length=50), nullable=True),
            sa.Column("is_under_warranty", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column("warranty_notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_device_registry_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="fk_maintenance_device_registry_customer_id_customers",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="fk_maintenance_device_registry_product_id_products",
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("tenant_id", "serial_number", name="uq_maintenance_device_registry_tenant_serial"),
        )

    # ── maintenance_purchase_orders ──
    if not _table_exists("maintenance_purchase_orders"):
        op.create_table(
            "maintenance_purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("branch_id", sa.Integer(), nullable=True, index=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True, index=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True, index=True),
            sa.Column("supplier_name", sa.String(length=200), nullable=True),
            sa.Column("po_number", sa.String(length=50), nullable=False, index=True),
            sa.Column(
                "order_date",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.Column("status", sa.String(length=20), nullable=False, default="draft", index=True),
            sa.Column("subtotal", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, default=0),
            sa.Column("tax_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("total_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("taxable_amount", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("currency", sa.String(length=3), nullable=False, default="AED"),
            sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=False, default=1),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("received_by", sa.Integer(), nullable=True, index=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gl_posted", sa.Boolean(), nullable=False, default=False),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_purchase_orders_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="fk_maintenance_purchase_orders_branch_id_branches",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="fk_maintenance_purchase_orders_warehouse_id_warehouses",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["supplier_id"],
                ["suppliers.id"],
                name="fk_maintenance_purchase_orders_supplier_id_suppliers",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["received_by"],
                ["users.id"],
                name="fk_maintenance_purchase_orders_received_by_users",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("tenant_id", "po_number", name="uq_maintenance_purchase_orders_tenant_number"),
        )
        op.create_index(
            "idx_maintenance_purchase_orders_tenant_status",
            "maintenance_purchase_orders",
            ["tenant_id", "status"],
        )

    # ── maintenance_purchase_order_lines ──
    if not _table_exists("maintenance_purchase_order_lines"):
        op.create_table(
            "maintenance_purchase_order_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("product_id", sa.Integer(), nullable=False, index=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True, index=True),
            sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False, default=1),
            sa.Column("unit_cost", sa.Numeric(precision=15, scale=4), nullable=False, default=0),
            sa.Column("line_total", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("movement_id", sa.Integer(), nullable=True),
            sa.Column("received_quantity", sa.Numeric(precision=15, scale=3), nullable=False, default=0),
            sa.Column("is_archived", sa.Boolean(), nullable=False, default=False, index=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_purchase_order_lines_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["purchase_order_id"],
                ["maintenance_purchase_orders.id"],
                name="fk_mnt_purchase_order_lines_purchase_order_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="fk_maintenance_purchase_order_lines_product_id_products",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="fk_maintenance_purchase_order_lines_warehouse_id_warehouses",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["movement_id"],
                ["stock_movements.id"],
                name="fk_maintenance_purchase_order_lines_movement_id_stock_movements",
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "idx_maintenance_purchase_order_lines_order",
            "maintenance_purchase_order_lines",
            ["tenant_id", "purchase_order_id"],
        )

    # ── maintenance_warranty_audit ──
    if not _table_exists("maintenance_warranty_audit"):
        op.create_table(
            "maintenance_warranty_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("maintenance_order_id", sa.Integer(), nullable=True, index=True),
            sa.Column("product_id", sa.Integer(), nullable=True, index=True),
            sa.Column("serial_number", sa.String(length=100), nullable=True, index=True),
            sa.Column("imei", sa.String(length=100), nullable=True, index=True),
            sa.Column("action", sa.String(length=50), nullable=False, index=True),
            sa.Column("from_status", sa.String(length=50), nullable=True),
            sa.Column("to_status", sa.String(length=50), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("performed_by", sa.Integer(), nullable=False, index=True),
            sa.Column(
                "performed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                default=sa.text("now()"),
                index=True,
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_maintenance_warranty_audit_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["maintenance_order_id"],
                ["maintenance_orders.id"],
                name="fk_maintenance_warranty_audit_order_id_maintenance_orders",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="fk_maintenance_warranty_audit_product_id_products",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["performed_by"],
                ["users.id"],
                name="fk_maintenance_warranty_audit_performed_by_users",
                ondelete="RESTRICT",
            ),
        )
    _install_warranty_audit_guards()
    _install_archive_only_guards()
    # The statutory artifact of a maintenance invoice hangs off the
    # maintenance document, so the e-invoice table carries the link.
    _add_maintenance_einvoice_link()


def downgrade() -> None:
    # Refuse rather than delete mappings when a tenant has started using them.
    _rebuild_concept_check(include_maintenance=False)
    _widen_stock_movement_type_constraint(include_maintenance=False)
    # The e-invoice rows of the maintenance invoices go with the invoices.
    if _table_exists("e_invoices") and _column_exists("e_invoices", "maintenance_invoice_id"):
        with op.batch_alter_table("e_invoices", schema=None) as batch_op:
            batch_op.drop_index("ix_e_invoices_maintenance_invoice_id")
            batch_op.drop_column("maintenance_invoice_id")
    bind = op.get_bind()
    for code, _name, _name_ar, _type, _level, _parent in _MAINTENANCE_ACCOUNTS:
        bind.execute(
            sa.text(
                "DELETE FROM gl_account_mappings WHERE tenant_id IN "
                "(SELECT id FROM tenants) AND gl_account_id IN "
                "(SELECT id FROM gl_accounts WHERE code = :c) AND concept_code IN ({})".format(
                    ", ".join(f"'{concept}'" for concept in sorted(_MAINTENANCE_CONCEPTS))
                )
            ),
            {"c": code},
        )
        bind.execute(sa.text("DELETE FROM gl_accounts WHERE code = :c"), {"c": code})
    for table in (
        "maintenance_purchase_order_lines",
        "maintenance_purchase_orders",
        "maintenance_warranty_audit",
        "maintenance_device_registry",
        "maintenance_services",
        "maintenance_settings",
        "maintenance_return_lines",
        "maintenance_returns",
        "maintenance_invoices",
        "maintenance_receipts",
        "maintenance_order_status_logs",
        "maintenance_order_services",
        "maintenance_order_lines",
        "maintenance_orders",
    ):
        if _table_exists(table):
            op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS prevent_maintenance_warranty_audit_change()")
        op.execute("DROP FUNCTION IF EXISTS prevent_maintenance_record_delete()")
    if _column_exists("tenants", "enable_maintenance"):
        with op.batch_alter_table("tenants", schema=None) as batch_op:
            batch_op.drop_column("enable_maintenance")
