"""Payroll statutory tax and social insurance.

Adds the columns the payroll engine needs to compute and persist the
statutory withholdings withheld from the employee and payable by the
employer - the tax auditors' projection gets its own columns rather than
burying everything in ``deductions`` (which preserves manual overrides).

Also widens the concept allow-list (``ck_gl_account_mappings_concept_code``)
for the new payroll statutory concepts and inserts the new GL accounts for
every tenant that already has a chart of accounts. New tenants get the
accounts from the updated ``BASE_ACCOUNTS`` automatically at provisioning.

Revision ID: f6a7b8c9d012
Revises: e2f3a4b5c6d7
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d012"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_EMPLOYEE_COL = {
    "name": "is_national",
    "type": sa.Boolean,
    "default": sa.text("false"),
}

_PAYROLL_COLS = (
    "income_tax_amount",
    "social_insurance_amount",
    "social_insurance_employer_amount",
)

_CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
_TABLE = "gl_account_mappings"


def _new_check_expression() -> str:
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


_NEW_ACCOUNTS = [
    # code, name, name_ar, type, sub_type, parent_code
    (
        "6221",
        "Employer Social Insurance Expense",
        "مصروف التأمينات الاجتماعية لصاحب العمل",
        "expense",
        "operating",
        "6200",
    ),
    (
        "2143",
        "Employee Social Insurance Payable",
        "اشتراكات التأمينات الاجتماعية الموظف",
        "liability",
        "payable",
        "2100",
    ),
    (
        "2144",
        "Employer Social Insurance Payable",
        "اشتراكات التأمينات الاجتماعية صاحب العمل",
        "liability",
        "payable",
        "2100",
    ),
    ("2147", "Payroll Income Tax Payable", "ضريبة دخل الموظفين مستحقة", "liability", "payable", "2100"),
]


def upgrade():
    bind = op.get_bind()

    # 1. employees.is_national — drives GOSI/GPSSA eligibility for SA/AE.
    inspector = sa.inspect(bind)
    employee_cols = {c["name"] for c in inspector.get_columns("employees")}
    if "is_national" not in employee_cols:
        with op.batch_alter_table("employees") as batch_op:
            batch_op.add_column(sa.Column("is_national", sa.Boolean(), nullable=True, server_default="false"))

    # 2. payroll_transactions — statutory columns.
    inspector = sa.inspect(bind)
    payroll_cols = {c["name"] for c in inspector.get_columns("payroll_transactions")}
    with op.batch_alter_table("payroll_transactions") as batch_op:
        for name in _PAYROLL_COLS:
            if name not in payroll_cols:
                batch_op.add_column(sa.Column(name, sa.Numeric(15, 3), nullable=False, server_default=sa.text("0")))

    # 3. New GL accounts for every tenant that already has a chart.
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

    # 4. Widen the concept CHECK constraint — drop and recreate from the
    #    model's own registry, the same rebuild pattern earlier widenings use.
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
                    )
                )
            ),
        )

    with op.batch_alter_table("payroll_transactions") as batch_op:
        for name in _PAYROLL_COLS:
            batch_op.drop_column(name)

    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_column("is_national")
