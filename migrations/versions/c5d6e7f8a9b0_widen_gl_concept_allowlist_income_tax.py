"""Widen the GL concept allow-list for income-tax concepts.

services/income_tax_service.py posts the corporate income-tax provision
with the concept codes INCOME_TAX_EXPENSE and INCOME_TAX_PAYABLE. The
registry (models/_constants.py) and the module mappings
(models/gl_account_registry.py income_tax) were widened to carry those
concepts, but gl_account_mappings.concept_code still carries the
allow-list built by d7e8f9a0b1c2 (plus a7b8c9d0e1f2, which touched no
concepts), so PostgreSQL would refuse any mapping row for the two new
concepts and abort the whole provisioning transaction.

This revision rebuilds ck_gl_account_mappings_concept_code from
GL_CONCEPT_CODES — the same list the model builds its CHECK from — so
the database accepts exactly the concepts the model says are valid.

Revision ID: c5d6e7f8a9b0
Revises: a7b8c9d0e1f2
"""

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
TABLE_NAME = "gl_account_mappings"

# The allow-list as of a7b8c9d0e1f2 (before INCOME_TAX_EXPENSE and
# INCOME_TAX_PAYABLE were added to GL_CONCEPT_CODES). Restored on
# downgrade.
_PREVIOUS_CONCEPTS = (
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
)


def _concept_check_expression() -> str:
    """The constraint expression, built from the same list the model uses."""
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


def _previous_check_expression() -> str:
    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in _PREVIOUS_CONCEPTS))


def upgrade():
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        _concept_check_expression(),
    )


def downgrade():
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        _previous_check_expression(),
    )
