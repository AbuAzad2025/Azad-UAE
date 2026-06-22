"""Update GL account mapping check constraint for new concepts

Revision ID: gl_mapping_004_update_ck_constraint
Revises: gl_mapping_003
Create Date: 2026-06-21

Adds END_OF_SERVICE_LIABILITY to the check constraint.
"""
from alembic import op
import sqlalchemy as sa

revision = 'gl_mapping_004_update_ck_constraint'
down_revision = 'gl_mapping_003'
branch_labels = None
depends_on = None


def upgrade():
    # Drop old check constraint and recreate with new concept list
    op.drop_constraint('ck_gl_account_mappings_concept_code', 'gl_account_mappings', type_='check')
    
    # Build updated check constraint with all current concepts
    # Must match models/_constants.py GL_CONCEPT_CODES
    concepts = [
        'AR', 'AP', 'CASH', 'BANK', 'INVENTORY_ASSET', 'COGS', 'COGS_REVERSAL',
        'SALES_REVENUE', 'SALES_RETURNS', 'SALES_DISCOUNT', 'VAT_INPUT', 'VAT_OUTPUT',
        'FX_GAIN', 'FX_LOSS', 'CHEQUES_UNDER_COLLECTION', 'INVENTORY_ADJUSTMENT_GAIN',
        'INVENTORY_ADJUSTMENT_LOSS', 'FREIGHT_IN', 'CUSTOMS_DUTY', 'DEFERRED_CHEQUES_PAYABLE',
        'PARTNER_CURRENT_ACCOUNT', 'MERCHANT_CURRENT_ACCOUNT', 'SHIPPING_REVENUE',
        'MISC_EXPENSE', 'COMMISSION_EXPENSE', 'EMPLOYEE_ADVANCES', 'PAYROLL_EXPENSE',
        'PAYROLL_PAYABLE', 'BANK_FEES', 'BANK_INTEREST_INCOME', 'DONATION_REVENUE',
        'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE', 'ACCUMULATED_DEPRECIATION',
        'FIXED_ASSET_GAIN', 'FIXED_ASSET_LOSS', 'SHOP_SALES_REVENUE', 'COUPON_EXPENSE',
        'LOYALTY_LIABILITY', 'SHIPPING_COST_EXPENSE', 'CAMPAIGN_DISCOUNT_EXPENSE',
        'WARRANTY_CLAIM_EXPENSE', 'PURCHASE_RETURNS', 'SALES_COMMISSION', 'TIER_DISCOUNT',
        'CARD_PROCESSING_FEES', 'PURCHASES', 'LANDED_COST', 'FOOD_SALES_REVENUE',
        'BEVERAGE_SALES_REVENUE', 'POS_CASH_DIFFERENCE', 'AZAD_PLATFORM_PAYABLE',
        'AZAD_PLATFORM_FEE_ACCRUED', 'AZAD_PLATFORM_FEE_PAID', 'AZAD_SUBSCRIPTION_EXPENSE',
        'AZAD_SUBSCRIPTION_REVENUE', 'OPENING_BALANCE_EQUITY', 'ACCOUNTS_PAYABLE',
        'END_OF_SERVICE_PROVISION', 'END_OF_SERVICE_LIABILITY', 'LEAVE_ACCRUAL_LIABILITY',
    ]
    
    concept_list = ', '.join(f"'{c}'" for c in concepts)
    
    op.create_check_constraint(
        'ck_gl_account_mappings_concept_code',
        'gl_account_mappings',
        sa.text(f"concept_code IN ({concept_list})")
    )


def downgrade():
    # Revert to previous concept list (without END_OF_SERVICE_LIABILITY)
    op.drop_constraint('ck_gl_account_mappings_concept_code', 'gl_account_mappings', type_='check')
    
    concepts = [
        'AR', 'AP', 'CASH', 'BANK', 'INVENTORY_ASSET', 'COGS', 'COGS_REVERSAL',
        'SALES_REVENUE', 'SALES_RETURNS', 'SALES_DISCOUNT', 'VAT_INPUT', 'VAT_OUTPUT',
        'FX_GAIN', 'FX_LOSS', 'CHEQUES_UNDER_COLLECTION', 'INVENTORY_ADJUSTMENT_GAIN',
        'INVENTORY_ADJUSTMENT_LOSS', 'FREIGHT_IN', 'CUSTOMS_DUTY', 'DEFERRED_CHEQUES_PAYABLE',
        'PARTNER_CURRENT_ACCOUNT', 'MERCHANT_CURRENT_ACCOUNT', 'SHIPPING_REVENUE',
        'MISC_EXPENSE', 'COMMISSION_EXPENSE', 'EMPLOYEE_ADVANCES', 'PAYROLL_EXPENSE',
        'PAYROLL_PAYABLE', 'BANK_FEES', 'BANK_INTEREST_INCOME', 'DONATION_REVENUE',
        'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE', 'ACCUMULATED_DEPRECIATION',
        'FIXED_ASSET_GAIN', 'FIXED_ASSET_LOSS', 'SHOP_SALES_REVENUE', 'COUPON_EXPENSE',
        'LOYALTY_LIABILITY', 'SHIPPING_COST_EXPENSE', 'CAMPAIGN_DISCOUNT_EXPENSE',
        'WARRANTY_CLAIM_EXPENSE', 'PURCHASE_RETURNS', 'SALES_COMMISSION', 'TIER_DISCOUNT',
        'CARD_PROCESSING_FEES', 'PURCHASES', 'LANDED_COST', 'FOOD_SALES_REVENUE',
        'BEVERAGE_SALES_REVENUE', 'POS_CASH_DIFFERENCE', 'AZAD_PLATFORM_PAYABLE',
        'AZAD_PLATFORM_FEE_ACCRUED', 'AZAD_PLATFORM_FEE_PAID', 'AZAD_SUBSCRIPTION_EXPENSE',
        'AZAD_SUBSCRIPTION_REVENUE', 'OPENING_BALANCE_EQUITY', 'ACCOUNTS_PAYABLE',
        'END_OF_SERVICE_PROVISION', 'LEAVE_ACCRUAL_LIABILITY',
    ]
    
    concept_list = ', '.join(f"'{c}'" for c in concepts)
    
    op.create_check_constraint(
        'ck_gl_account_mappings_concept_code',
        'gl_account_mappings',
        sa.text(f"concept_code IN ({concept_list})")
    )
