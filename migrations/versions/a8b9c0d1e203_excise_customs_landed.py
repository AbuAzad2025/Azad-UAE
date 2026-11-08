"""Import-time excise duty on purchases + excise classification on products.

Adds ``purchases.excise_amount`` (part of the landed cost, same treatment as
customs duty), ``products.excise_category`` (tobacco / energy_drinks /
soft_drinks — import-time levies only, they never apply to a retail sale),
the ``EXCISE_DUTY`` concept to the allow-list, and account ``5304``
("Excise Duty") for every tenant that already has a chart. New tenants get
the account from ``BASE_ACCOUNTS`` at provisioning.

Revision ID: a8b9c0d1e203
Revises: f6a7b8c9d012
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e203"
down_revision = "f6a7b8c9d012"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
_TABLE = "gl_account_mappings"


def _new_check_expression() -> str:
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. products.excise_category
    product_cols = {c["name"] for c in inspector.get_columns("products")}
    if "excise_category" not in product_cols:
        with op.batch_alter_table("products") as batch_op:
            batch_op.add_column(sa.Column("excise_category", sa.String(20), nullable=True))

    # 2. purchases.excise_amount
    purchase_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "excise_amount" not in purchase_cols:
        with op.batch_alter_table("purchases") as batch_op:
            batch_op.add_column(
                sa.Column("excise_amount", sa.Numeric(15, 3), nullable=False, server_default=sa.text("0"))
            )

    # 3. Account 5304 for every tenant that already has a chart.
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
        exists = bind.execute(
            sa.text("SELECT 1 FROM gl_accounts WHERE tenant_id = :t AND code = '5304' LIMIT 1"),
            {"t": tenant_id},
        ).first()
        if exists:
            continue
        parent_id = bind.execute(
            sa.text("SELECT id FROM gl_accounts WHERE tenant_id = :t AND code = '5300' LIMIT 1"),
            {"t": tenant_id},
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
                    (:t, '5304', 'Excise Duty', 'رسوم انتقائية', 'expense', 'operating',
                     false, :pid, true, false,
                     NULL, false, false,
                     :cur, 2,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"t": tenant_id, "pid": parent_id, "cur": currency},
        )

    # 4. Widen the concept CHECK constraint again — rebuilt from the model's
    #    own registry, same pattern as the previous widenings.
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
                    )
                )
            ),
        )

    with op.batch_alter_table("purchases") as batch_op:
        batch_op.drop_column("excise_amount")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("excise_category")
