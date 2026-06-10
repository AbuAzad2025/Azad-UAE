"""Phase GL.3: extend GL mapping concept registry for unified inventory

Revision ID: gl_mapping_003
Revises: gl_mapping_002
Create Date: 2026-06-10

Adds concept codes required by the unified inventory plan:
  campaigns, warranty, shipments, card payments, tier discounts, sales commissions,
  purchase returns, landed cost, shop online, loyalty.
"""
from alembic import op


revision = 'gl_mapping_003'
down_revision = 'gl_mapping_002'
branch_labels = None
depends_on = None


OLD_GL_CONCEPT_CODES = (
    'AR',
    'AP',
    'CASH',
    'BANK',
    'INVENTORY_ASSET',
    'COGS',
    'COGS_REVERSAL',
    'SALES_REVENUE',
    'SALES_RETURNS',
    'SALES_DISCOUNT',
    'VAT_INPUT',
    'VAT_OUTPUT',
    'FX_GAIN',
    'FX_LOSS',
    'CHEQUES_UNDER_COLLECTION',
    'INVENTORY_ADJUSTMENT_GAIN',
    'INVENTORY_ADJUSTMENT_LOSS',
    'FREIGHT_IN',
    'CUSTOMS_DUTY',
    'DEFERRED_CHEQUES_PAYABLE',
    'PARTNER_CURRENT_ACCOUNT',
    'MERCHANT_CURRENT_ACCOUNT',
    'SHIPPING_REVENUE',
    'MISC_EXPENSE',
    'COMMISSION_EXPENSE',
    'EMPLOYEE_ADVANCES',
    'PAYROLL_EXPENSE',
    'PAYROLL_PAYABLE',
    'BANK_FEES',
    'BANK_INTEREST_INCOME',
    'DONATION_REVENUE',
    'FIXED_ASSET_ASSET',
    'DEPRECIATION_EXPENSE',
    'ACCUMULATED_DEPRECIATION',
    'FIXED_ASSET_GAIN',
    'FIXED_ASSET_LOSS',
)

NEW_GL_CONCEPT_CODES = OLD_GL_CONCEPT_CODES + (
    'SHOP_SALES_REVENUE',
    'COUPON_EXPENSE',
    'LOYALTY_LIABILITY',
    'SHIPPING_COST_EXPENSE',
    'CAMPAIGN_DISCOUNT_EXPENSE',
    'WARRANTY_CLAIM_EXPENSE',
    'PURCHASE_RETURNS',
    'SALES_COMMISSION',
    'TIER_DISCOUNT',
    'CARD_PROCESSING_FEES',
    'PURCHASES',
    'LANDED_COST',
)


def _concept_check(codes):
    return "concept_code IN ({})".format(
        ", ".join(f"'{code}'" for code in codes)
    )


def upgrade():
    with op.batch_alter_table('gl_account_mappings') as batch_op:
        batch_op.drop_constraint(
            'ck_gl_account_mappings_concept_code',
            type_='check',
        )
        batch_op.create_check_constraint(
            'ck_gl_account_mappings_concept_code',
            _concept_check(NEW_GL_CONCEPT_CODES),
        )


def downgrade():
    with op.batch_alter_table('gl_account_mappings') as batch_op:
        batch_op.drop_constraint(
            'ck_gl_account_mappings_concept_code',
            type_='check',
        )
        batch_op.create_check_constraint(
            'ck_gl_account_mappings_concept_code',
            _concept_check(OLD_GL_CONCEPT_CODES),
        )
