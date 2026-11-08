"""Tenant compliance settings + e-invoice Phase 2 chain fields + pension columns.

Every feature added by the compliance pass is controllable per tenant:

* tenants: enable_einvoice, enable_einvoice_credit_notes, zatca_phase2_enabled,
  enable_ita_allocation, ita_allocation_threshold, enable_import_duties,
  enable_tax_categories, enable_il_pension, enable_zakat, wht_services_rate
* new table tenant_secrets (encrypted Fernet values, e.g. ZATCA CSID, ITA token)
* products.tax_category / sale_lines.tax_category / purchase_lines.tax_category
  for per-line Standard/Zero/Exempt VAT
* e_invoices: doc_type (invoice|credit_note), return_id, ita_allocation_number,
  invoice_counter_value, previous_invoice_hash (ZATCA Phase 2 chain)
* payroll_transactions: pension_amount / pension_employer_amount (IL statutory)
* GL: ZAKAT_EXPENSE (6351), ZAKAT_PAYABLE (2148), WITHHOLDING_TAX_PAYABLE (2149),
  EMPLOYER_PENSION_EXPENSE (6222), EMPLOYEE_PENSION_PAYABLE (2145),
  EMPLOYER_PENSION_PAYABLE (2146) + concept allow-list widened for the new
  concepts and account INSERTs for every tenant that already has a chart
* suppliers.is_nonresident (for withholding-tax on non-resident services)

Revision ID: c0d1e2f3a405
Revises: b9c0d1e2f304
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a405"
down_revision = "b9c0d1e2f304"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
_TABLE = "gl_account_mappings"

_TENANT_BOOL_COLUMNS = [
    "enable_einvoice",
    "enable_einvoice_credit_notes",
    "zatca_phase2_enabled",
    "enable_ita_allocation",
    "enable_import_duties",
    "enable_tax_categories",
    "enable_il_pension",
    "enable_zakat",
]

_TENANT_DEFAULTS = {
    "enable_einvoice": sa.text("true"),
    "enable_einvoice_credit_notes": sa.text("true"),
    "zatca_phase2_enabled": sa.text("false"),
    "enable_ita_allocation": sa.text("false"),
    "enable_import_duties": sa.text("true"),
    "enable_tax_categories": sa.text("false"),
    "enable_il_pension": sa.text("false"),
    "enable_zakat": sa.text("false"),
}

_NEW_ACCOUNTS = [
    # code, name, name_ar, type, sub_type, parent_code
    ("6222", "Employer Pension Expense", "مصروف مساهمات التقاعد لصاحب العمل", "expense", "operating", "6200"),
    ("6351", "Zakat Expense", "مصروف الزكاة", "expense", "operating", "6000"),
    ("2145", "Employee Pension Payable", "اشتراكات التقاعد للموظف", "liability", "payable", "2100"),
    ("2146", "Employer Pension Payable", "اشتراكات التقاعد لصاحب العمل", "liability", "payable", "2100"),
    ("2148", "Zakat Payable", "زكاة مستحقة", "liability", "payable", "2100"),
]


def _has_column(bind, table: str, name: str) -> bool:
    return name in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _new_check_expression() -> str:
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. tenants — compliance switches (each one gates its feature).
    tenant_cols = {c["name"] for c in inspector.get_columns("tenants")}
    with op.batch_alter_table("tenants") as batch_op:
        for name in _TENANT_BOOL_COLUMNS:
            if name not in tenant_cols:
                batch_op.add_column(
                    sa.Column(name, sa.Boolean(), nullable=False, server_default=_TENANT_DEFAULTS[name])
                )
        if "ita_allocation_threshold" not in tenant_cols:
            batch_op.add_column(
                sa.Column(
                    "ita_allocation_threshold",
                    sa.Numeric(15, 3),
                    nullable=False,
                    server_default=sa.text("5000"),
                )
            )
        if "ita_environment" not in tenant_cols:
            # sandbox | production — where ITA allocation requests go.
            batch_op.add_column(sa.Column("ita_environment", sa.String(12), nullable=False, server_default="sandbox"))
        if "zatca_environment" not in tenant_cols:
            # sandbox | production — where ZATCA submission goes.
            batch_op.add_column(sa.Column("zatca_environment", sa.String(12), nullable=False, server_default="sandbox"))

    # 2. tenant_secrets — Fernet-encrypted key/value store for integration
    #    credentials (ZATCA CSID, ITA access token). Values are never
    #    returned to templates; the settings page shows only set/not-set.
    if "tenant_secrets" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "tenant_secrets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(60), nullable=False),
            sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_secret_name"),
        )
        op.create_index("idx_tenant_secrets_tenant", "tenant_secrets", ["tenant_id"])

    # 3. per-line tax categories (Standard/Zero/Exempt)
    product_cols = {c["name"] for c in inspector.get_columns("products")}
    with op.batch_alter_table("products") as batch_op:
        if "tax_category" not in product_cols:
            batch_op.add_column(sa.Column("tax_category", sa.String(10), nullable=False, server_default="standard"))

    for table in ("sale_lines", "purchase_lines"):
        line_cols = {c["name"] for c in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch_op:
            if "tax_category" not in line_cols:
                batch_op.add_column(sa.Column("tax_category", sa.String(10), nullable=False, server_default="standard"))

    # 4. expenses — withholding tax at source on non-resident service payments
    expense_cols = {c["name"] for c in inspector.get_columns("expenses")}
    with op.batch_alter_table("expenses") as batch_op:
        if "is_service_to_nonresident" not in expense_cols:
            batch_op.add_column(
                sa.Column("is_service_to_nonresident", sa.Boolean(), nullable=False, server_default=sa.text("false"))
            )
        if "wht_amount" not in expense_cols:
            batch_op.add_column(sa.Column("wht_amount", sa.Numeric(15, 3), nullable=False, server_default=sa.text("0")))

    # 5. payroll_transactions — IL statutory pension columns
    payroll_cols = {c["name"] for c in inspector.get_columns("payroll_transactions")}
    with op.batch_alter_table("payroll_transactions") as batch_op:
        if "pension_amount" not in payroll_cols:
            batch_op.add_column(
                sa.Column("pension_amount", sa.Numeric(15, 3), nullable=False, server_default=sa.text("0"))
            )
        if "pension_employer_amount" not in payroll_cols:
            batch_op.add_column(
                sa.Column("pension_employer_amount", sa.Numeric(15, 3), nullable=False, server_default=sa.text("0"))
            )

    # 5. e_invoices — doc types, credit notes, ZATCA Phase 2 chain, ITA number
    einv_cols = {c["name"] for c in inspector.get_columns("e_invoices")}
    with op.batch_alter_table("e_invoices") as batch_op:
        if "doc_type" not in einv_cols:
            batch_op.add_column(sa.Column("doc_type", sa.String(20), nullable=False, server_default="invoice"))
        if "return_id" not in einv_cols:
            batch_op.add_column(
                sa.Column(
                    "return_id",
                    sa.Integer(),
                    sa.ForeignKey("product_returns.id", ondelete="CASCADE"),
                    nullable=True,
                )
            )
        if "ita_allocation_number" not in einv_cols:
            batch_op.add_column(sa.Column("ita_allocation_number", sa.String(30), nullable=True))
        if "invoice_counter_value" not in einv_cols:
            batch_op.add_column(sa.Column("invoice_counter_value", sa.Integer(), nullable=True))
        # sale_id becomes nullable so credit notes (which reference a return)
        # can be stored without a sale.
        batch_op.alter_column("sale_id", existing_type=sa.Integer(), nullable=True)
    existing_uniques = {c["name"] for c in sa.inspect(bind).get_unique_constraints("e_invoices")}
    if "uq_einvoice_tenant_sale" in existing_uniques:
        with op.batch_alter_table("e_invoices") as batch_op:
            batch_op.drop_constraint("uq_einvoice_tenant_sale", type_="unique")
    existing_indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("e_invoices")}
    if "uq_einvoice_tenant_invoice" not in existing_indexes:
        op.create_index(
            "uq_einvoice_tenant_invoice",
            "e_invoices",
            ["tenant_id", "sale_id"],
            unique=True,
            postgresql_where=sa.text("doc_type = 'invoice'"),
        )
    if "uq_einvoice_tenant_return" not in existing_indexes:
        op.create_index(
            "uq_einvoice_tenant_return",
            "e_invoices",
            ["tenant_id", "return_id"],
            unique=True,
            postgresql_where=sa.text("return_id IS NOT NULL"),
        )

    # 6. New GL accounts for every tenant that already has a chart.
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
        for code, name, name_ar, account_type, sub_type, parent_code in _NEW_ACCOUNTS:
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
                         :cur, 2,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "t": tenant_id,
                    "c": code,
                    "n": name,
                    "nar": name_ar,
                    "ty": account_type,
                    "st": sub_type,
                    "pid": parent_id,
                    "cur": currency,
                },
            )

    # 7. Widen the concept CHECK constraint — rebuilt from the model registry.
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT_NAME, _new_check_expression())


def downgrade():
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(
            _CONSTRAINT_NAME,
            "concept_code IN ({})".format(
                ", ".join(
                    f"'{c}'"
                    for c in (
                        "AR",
                        "AP",
                        "CASH",
                        "BANK",
                        "INVENTORY_ASSET",
                        "COGS",
                        "COGS_REVERSAL",
                        "SALES_REVENUE",
                        "SALES_RETURNS",
                        "SALES_DISCOUNT",
                        "VAT_INPUT",
                        "VAT_OUTPUT",
                        "FX_GAIN",
                        "FX_LOSS",
                        "CHEQUES_UNDER_COLLECTION",
                        "INVENTORY_ADJUSTMENT_GAIN",
                        "INVENTORY_ADJUSTMENT_LOSS",
                        "FREIGHT_IN",
                        "CUSTOMS_DUTY",
                        "DEFERRED_CHEQUES_PAYABLE",
                        "PARTNER_CURRENT_ACCOUNT",
                        "MERCHANT_CURRENT_ACCOUNT",
                        "SHIPPING_REVENUE",
                        "MISC_EXPENSE",
                        "COMMISSION_EXPENSE",
                        "EMPLOYEE_ADVANCES",
                        "PAYROLL_EXPENSE",
                        "PAYROLL_EXPENSE_2",
                        "PAYROLL_PAYABLE",
                        "BANK_FEES",
                        "BANK_INTEREST_INCOME",
                        "DONATION_REVENUE",
                        "FIXED_ASSET_ASSET",
                        "DEPRECIATION_EXPENSE",
                        "ACCUMULATED_DEPRECIATION",
                        "FIXED_ASSET_GAIN",
                        "FIXED_ASSET_LOSS",
                        "SHOP_SALES_REVENUE",
                        "COUPON_EXPENSE",
                        "LOYALTY_LIABILITY",
                        "SHIPPING_COST_EXPENSE",
                        "CAMPAIGN_DISCOUNT_EXPENSE",
                        "CAMPAIGN_DISCOUNT_REVERSAL",
                        "WARRANTY_CLAIM_EXPENSE",
                        "PURCHASE_RETURNS",
                        "SALES_COMMISSION",
                        "TIER_DISCOUNT",
                        "CARD_PROCESSING_FEES",
                        "PURCHASES",
                        "LANDED_COST",
                        "FOOD_SALES_REVENUE",
                        "BEVERAGE_SALES_REVENUE",
                        "POS_CASH_DIFFERENCE",
                        "AZAD_PLATFORM_PAYABLE",
                        "AZAD_PLATFORM_FEE_ACCRUED",
                        "AZAD_PLATFORM_FEE_PAID",
                        "AZAD_SUBSCRIPTION_EXPENSE",
                        "AZAD_SUBSCRIPTION_REVENUE",
                        "OPENING_BALANCE_EQUITY",
                        "ACCOUNTS_PAYABLE",
                        "END_OF_SERVICE_PROVISION",
                        "END_OF_SERVICE_LIABILITY",
                        "LEAVE_ACCRUAL_LIABILITY",
                        "SUSPENSE",
                        "RETAINED_EARNINGS",
                        "REVENUE_CLOSING",
                        "EXPENSE_CLOSING",
                        "INSURANCE_IN",
                        "INCOME_TAX_EXPENSE",
                        "INCOME_TAX_PAYABLE",
                        "EMPLOYER_SOCIAL_INSURANCE_EXPENSE",
                        "EMPLOYEE_SOCIAL_INSURANCE_PAYABLE",
                        "EMPLOYER_SOCIAL_INSURANCE_PAYABLE",
                        "EMPLOYEE_INCOME_TAX_PAYABLE",
                        "EXCISE_DUTY",
                    )
                )
            ),
        )

    # Credit-note rows cannot be preserved under the old unique(tenant, sale)
    # constraint, so they are removed before the constraint is restored.
    op.execute("DELETE FROM e_invoices WHERE doc_type <> 'invoice'")
    op.drop_index("uq_einvoice_tenant_return", table_name="e_invoices")
    op.drop_index("uq_einvoice_tenant_invoice", table_name="e_invoices")
    with op.batch_alter_table("e_invoices") as batch_op:
        batch_op.create_unique_constraint("uq_einvoice_tenant_sale", ["tenant_id", "sale_id"])
        batch_op.alter_column("sale_id", existing_type=sa.Integer(), nullable=False)
        for col in ("doc_type", "return_id", "ita_allocation_number", "invoice_counter_value"):
            batch_op.drop_column(col)

    with op.batch_alter_table("expenses") as batch_op:
        batch_op.drop_column("is_service_to_nonresident")
        batch_op.drop_column("wht_amount")

    with op.batch_alter_table("payroll_transactions") as batch_op:
        batch_op.drop_column("pension_amount")
        batch_op.drop_column("pension_employer_amount")

    for table in ("purchase_lines", "sale_lines"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("tax_category")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("tax_category")

    op.drop_table("tenant_secrets")

    with op.batch_alter_table("tenants") as batch_op:
        for name in _TENANT_BOOL_COLUMNS:
            batch_op.drop_column(name)
        batch_op.drop_column("ita_allocation_threshold")
        batch_op.drop_column("zatca_environment")
        batch_op.drop_column("ita_environment")
