"""Phase 1K.1: extend GL mapping concept registry constraint

Revision ID: gl_mapping_002
Revises: gl_mapping_001
Create Date: 2026-06-04 14:10:00.000000

Expands the allowed GLAccountMapping concept codes for the Phase 1K.1
posting-coverage concepts. This migration only changes the check constraint;
it does not seed, backfill, update postings, or modify historical data.
"""
from alembic import op


revision = 'gl_mapping_002'
down_revision = 'gl_mapping_001'
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
)

NEW_GL_CONCEPT_CODES = OLD_GL_CONCEPT_CODES + (
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
