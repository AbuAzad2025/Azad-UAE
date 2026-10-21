"""widen the GL concept allow-list - the registry and the database disagreed

``gl_account_mappings.concept_code`` carries a CHECK constraint that lists the
concepts a mapping row may name. The list was written in the baseline migration
and then drifted away from ``GL_CONCEPT_CODES`` in ``models/_constants.py``, in
two ways:

* ``PAYROLL_EXPENSE_2`` was added to the code list and to the concept registry
  but never to the constraint. A mapping row naming it therefore raised a
  ``CheckViolation`` - and because the check is on the table, that aborted the
  *whole* provisioning transaction rather than the one row.
* ``CAMPAIGN_DISCOUNT_REVERSAL`` was posted by ``services/return_service.py``
  and named by no list at all: not in the registry, not in the code list, not
  in the constraint. The resolver refuses a concept it does not know
  *unconditionally*, before the dynamic-mapping flag is even consulted, so a
  promotional sale's return could not be posted in either flag state and the
  whole return transaction failed.

This revision rebuilds the constraint from the code list, so the database
accepts exactly the concepts the model says are valid - and the model generates
the same expression from the same list, so the two cannot drift apart again.

The constraint is dropped and re-added rather than altered in place: PostgreSQL
has no "alter a check constraint" statement, and the table is small enough
that a rebuild is cheap. The rebuild is idempotent - the constraint is only
replaced when it exists.

Revision ID: c3d9e1f7a204
Revises: 5e2b8f4a6c13
"""

from alembic import op

revision = "c3d9e1f7a204"
down_revision = "5e2b8f4a6c13"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
TABLE_NAME = "gl_account_mappings"


def _concept_check_expression() -> str:
    """The constraint expression, built from the same list the model uses."""
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


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
        "concept_code IN ('AR', 'AP', 'CASH', 'BANK', 'INVENTORY_ASSET', 'COGS', 'COGS_REVERSAL', "
        "'SALES_REVENUE', 'SALES_RETURNS', 'SALES_DISCOUNT', 'VAT_INPUT', 'VAT_OUTPUT', 'FX_GAIN', "
        "'FX_LOSS', 'CHEQUES_UNDER_COLLECTION', 'INVENTORY_ADJUSTMENT_GAIN', 'INVENTORY_ADJUSTMENT_LOSS', "
        "'FREIGHT_IN', 'CUSTOMS_DUTY', 'DEFERRED_CHEQUES_PAYABLE', 'PARTNER_CURRENT_ACCOUNT', "
        "'MERCHANT_CURRENT_ACCOUNT', 'SHIPPING_REVENUE', 'MISC_EXPENSE', 'COMMISSION_EXPENSE', "
        "'EMPLOYEE_ADVANCES', 'PAYROLL_EXPENSE', 'PAYROLL_PAYABLE', 'BANK_FEES', 'BANK_INTEREST_INCOME', "
        "'DONATION_REVENUE', 'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE', 'ACCUMULATED_DEPRECIATION', "
        "'FIXED_ASSET_GAIN', 'FIXED_ASSET_LOSS', 'SHOP_SALES_REVENUE', 'COUPON_EXPENSE', 'LOYALTY_LIABILITY', "
        "'SHIPPING_COST_EXPENSE', 'CAMPAIGN_DISCOUNT_EXPENSE', 'WARRANTY_CLAIM_EXPENSE', 'PURCHASE_RETURNS', "
        "'SALES_COMMISSION', 'TIER_DISCOUNT', 'CARD_PROCESSING_FEES', 'PURCHASES', 'LANDED_COST', "
        "'FOOD_SALES_REVENUE', 'BEVERAGE_SALES_REVENUE', 'POS_CASH_DIFFERENCE', 'AZAD_PLATFORM_PAYABLE', "
        "'AZAD_PLATFORM_FEE_ACCRUED', 'AZAD_PLATFORM_FEE_PAID', 'AZAD_SUBSCRIPTION_EXPENSE', "
        "'AZAD_SUBSCRIPTION_REVENUE', 'OPENING_BALANCE_EQUITY', 'ACCOUNTS_PAYABLE', 'END_OF_SERVICE_PROVISION', "
        "'END_OF_SERVICE_LIABILITY', 'LEAVE_ACCRUAL_LIABILITY', 'SUSPENSE')",
    )
