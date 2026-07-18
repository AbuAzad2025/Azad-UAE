from __future__ import annotations

from typing import Any

GL_CONCEPT_AR = "AR"
GL_CONCEPT_AP = "AP"
GL_CONCEPT_CASH = "CASH"
GL_CONCEPT_BANK = "BANK"
GL_CONCEPT_INVENTORY_ASSET = "INVENTORY_ASSET"
GL_CONCEPT_COGS = "COGS"
GL_CONCEPT_COGS_REVERSAL = "COGS_REVERSAL"
GL_CONCEPT_SALES_REVENUE = "SALES_REVENUE"
GL_CONCEPT_SALES_RETURNS = "SALES_RETURNS"
GL_CONCEPT_SALES_DISCOUNT = "SALES_DISCOUNT"
GL_CONCEPT_VAT_INPUT = "VAT_INPUT"
GL_CONCEPT_VAT_OUTPUT = "VAT_OUTPUT"
GL_CONCEPT_FX_GAIN = "FX_GAIN"
GL_CONCEPT_FX_LOSS = "FX_LOSS"
GL_CONCEPT_CHEQUES_UNDER_COLLECTION = "CHEQUES_UNDER_COLLECTION"
GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN = "INVENTORY_ADJUSTMENT_GAIN"
GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS = "INVENTORY_ADJUSTMENT_LOSS"
GL_CONCEPT_FREIGHT_IN = "FREIGHT_IN"
GL_CONCEPT_CUSTOMS_DUTY = "CUSTOMS_DUTY"
GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE = "DEFERRED_CHEQUES_PAYABLE"
GL_CONCEPT_PARTNER_CURRENT_ACCOUNT = "PARTNER_CURRENT_ACCOUNT"
GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT = "MERCHANT_CURRENT_ACCOUNT"
GL_CONCEPT_SHIPPING_REVENUE = "SHIPPING_REVENUE"
GL_CONCEPT_MISC_EXPENSE = "MISC_EXPENSE"
GL_CONCEPT_COMMISSION_EXPENSE = "COMMISSION_EXPENSE"
GL_CONCEPT_EMPLOYEE_ADVANCES = "EMPLOYEE_ADVANCES"
GL_CONCEPT_PAYROLL_EXPENSE = "PAYROLL_EXPENSE"
GL_CONCEPT_PAYROLL_EXPENSE_2 = "PAYROLL_EXPENSE_2"
GL_CONCEPT_PAYROLL_PAYABLE = "PAYROLL_PAYABLE"
GL_CONCEPT_BANK_FEES = "BANK_FEES"
GL_CONCEPT_BANK_INTEREST_INCOME = "BANK_INTEREST_INCOME"
GL_CONCEPT_DONATION_REVENUE = "DONATION_REVENUE"
GL_CONCEPT_FIXED_ASSET_ASSET = "FIXED_ASSET_ASSET"
GL_CONCEPT_DEPRECIATION_EXPENSE = "DEPRECIATION_EXPENSE"
GL_CONCEPT_ACCUMULATED_DEPRECIATION = "ACCUMULATED_DEPRECIATION"
GL_CONCEPT_FIXED_ASSET_GAIN = "FIXED_ASSET_GAIN"
GL_CONCEPT_FIXED_ASSET_LOSS = "FIXED_ASSET_LOSS"
GL_CONCEPT_SHOP_SALES_REVENUE = "SHOP_SALES_REVENUE"
GL_CONCEPT_COUPON_EXPENSE = "COUPON_EXPENSE"
GL_CONCEPT_LOYALTY_LIABILITY = "LOYALTY_LIABILITY"
GL_CONCEPT_SHIPPING_COST_EXPENSE = "SHIPPING_COST_EXPENSE"
GL_CONCEPT_CAMPAIGN_DISCOUNT_EXPENSE = "CAMPAIGN_DISCOUNT_EXPENSE"
GL_CONCEPT_WARRANTY_CLAIM_EXPENSE = "WARRANTY_CLAIM_EXPENSE"
GL_CONCEPT_PURCHASE_RETURNS = "PURCHASE_RETURNS"
GL_CONCEPT_SALES_COMMISSION = "SALES_COMMISSION"
GL_CONCEPT_TIER_DISCOUNT = "TIER_DISCOUNT"
GL_CONCEPT_CARD_PROCESSING_FEES = "CARD_PROCESSING_FEES"
GL_CONCEPT_PURCHASES = "PURCHASES"
GL_CONCEPT_LANDED_COST = "LANDED_COST"
GL_CONCEPT_FOOD_SALES_REVENUE = "FOOD_SALES_REVENUE"
GL_CONCEPT_BEVERAGE_SALES_REVENUE = "BEVERAGE_SALES_REVENUE"
GL_CONCEPT_POS_CASH_DIFFERENCE = "POS_CASH_DIFFERENCE"
GL_CONCEPT_OPENING_BALANCE_EQUITY = "OPENING_BALANCE_EQUITY"
GL_CONCEPT_ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"
GL_CONCEPT_END_OF_SERVICE_PROVISION = "END_OF_SERVICE_PROVISION"
GL_CONCEPT_END_OF_SERVICE_LIABILITY = "END_OF_SERVICE_LIABILITY"
GL_CONCEPT_LEAVE_ACCRUAL_LIABILITY = "LEAVE_ACCRUAL_LIABILITY"
GL_CONCEPT_SUSPENSE = "SUSPENSE"

# Resolution modes for GL authority model
RESOLUTION_MODE_MAPPING = "mapping"
RESOLUTION_MODE_LIQUIDITY = "liquidity"
RESOLUTION_MODE_RECORD = "record"
RESOLUTION_MODE_NON_POSTING = "non_posting"
GL_CONCEPT_AZAD_PLATFORM_PAYABLE = "AZAD_PLATFORM_PAYABLE"
GL_CONCEPT_AZAD_PLATFORM_FEE_ACCRUED = "AZAD_PLATFORM_FEE_ACCRUED"
GL_CONCEPT_AZAD_PLATFORM_FEE_PAID = "AZAD_PLATFORM_FEE_PAID"
GL_CONCEPT_AZAD_SUBSCRIPTION_EXPENSE = "AZAD_SUBSCRIPTION_EXPENSE"
GL_CONCEPT_AZAD_SUBSCRIPTION_REVENUE = "AZAD_SUBSCRIPTION_REVENUE"

GL_CONCEPT_CODES = (
    GL_CONCEPT_AR,
    GL_CONCEPT_AP,
    GL_CONCEPT_CASH,
    GL_CONCEPT_BANK,
    GL_CONCEPT_INVENTORY_ASSET,
    GL_CONCEPT_COGS,
    GL_CONCEPT_COGS_REVERSAL,
    GL_CONCEPT_SALES_REVENUE,
    GL_CONCEPT_SALES_RETURNS,
    GL_CONCEPT_SALES_DISCOUNT,
    GL_CONCEPT_VAT_INPUT,
    GL_CONCEPT_VAT_OUTPUT,
    GL_CONCEPT_FX_GAIN,
    GL_CONCEPT_FX_LOSS,
    GL_CONCEPT_CHEQUES_UNDER_COLLECTION,
    GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN,
    GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS,
    GL_CONCEPT_FREIGHT_IN,
    GL_CONCEPT_CUSTOMS_DUTY,
    GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE,
    GL_CONCEPT_PARTNER_CURRENT_ACCOUNT,
    GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT,
    GL_CONCEPT_SHIPPING_REVENUE,
    GL_CONCEPT_MISC_EXPENSE,
    GL_CONCEPT_COMMISSION_EXPENSE,
    GL_CONCEPT_EMPLOYEE_ADVANCES,
    GL_CONCEPT_PAYROLL_EXPENSE,
    GL_CONCEPT_PAYROLL_EXPENSE_2,
    GL_CONCEPT_PAYROLL_PAYABLE,
    GL_CONCEPT_BANK_FEES,
    GL_CONCEPT_BANK_INTEREST_INCOME,
    GL_CONCEPT_DONATION_REVENUE,
    GL_CONCEPT_FIXED_ASSET_ASSET,
    GL_CONCEPT_DEPRECIATION_EXPENSE,
    GL_CONCEPT_ACCUMULATED_DEPRECIATION,
    GL_CONCEPT_FIXED_ASSET_GAIN,
    GL_CONCEPT_FIXED_ASSET_LOSS,
    GL_CONCEPT_SHOP_SALES_REVENUE,
    GL_CONCEPT_COUPON_EXPENSE,
    GL_CONCEPT_LOYALTY_LIABILITY,
    GL_CONCEPT_SHIPPING_COST_EXPENSE,
    GL_CONCEPT_CAMPAIGN_DISCOUNT_EXPENSE,
    GL_CONCEPT_WARRANTY_CLAIM_EXPENSE,
    GL_CONCEPT_PURCHASE_RETURNS,
    GL_CONCEPT_SALES_COMMISSION,
    GL_CONCEPT_TIER_DISCOUNT,
    GL_CONCEPT_CARD_PROCESSING_FEES,
    GL_CONCEPT_PURCHASES,
    GL_CONCEPT_LANDED_COST,
    GL_CONCEPT_FOOD_SALES_REVENUE,
    GL_CONCEPT_BEVERAGE_SALES_REVENUE,
    GL_CONCEPT_POS_CASH_DIFFERENCE,
    GL_CONCEPT_AZAD_PLATFORM_PAYABLE,
    GL_CONCEPT_AZAD_PLATFORM_FEE_ACCRUED,
    GL_CONCEPT_AZAD_PLATFORM_FEE_PAID,
    GL_CONCEPT_AZAD_SUBSCRIPTION_EXPENSE,
    GL_CONCEPT_AZAD_SUBSCRIPTION_REVENUE,
    GL_CONCEPT_OPENING_BALANCE_EQUITY,
    GL_CONCEPT_ACCOUNTS_PAYABLE,
    GL_CONCEPT_END_OF_SERVICE_PROVISION,
    GL_CONCEPT_END_OF_SERVICE_LIABILITY,
    GL_CONCEPT_LEAVE_ACCRUAL_LIABILITY,
    GL_CONCEPT_SUSPENSE,
)

GL_CONCEPT_REGISTRY: dict[str, dict[str, Any]] = {
    GL_CONCEPT_AR: {
        "meaning": "Accounts Receivable",
        "legacy_code": "1130",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AP: {
        "meaning": "Accounts Payable",
        "legacy_code": "2110",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_CASH: {
        "meaning": "Cash",
        "legacy_code": None,
        "required": True,
        "resolution_mode": RESOLUTION_MODE_LIQUIDITY,
    },
    GL_CONCEPT_BANK: {
        "meaning": "Bank",
        "legacy_code": "1120",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_LIQUIDITY,
    },
    GL_CONCEPT_INVENTORY_ASSET: {
        "meaning": "Inventory Asset",
        "legacy_code": "1140",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_COGS: {
        "meaning": "Cost of Goods Sold",
        "legacy_code": "5100",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_COGS_REVERSAL: {
        "meaning": "Cost of Goods Sold Reversal",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SALES_REVENUE: {
        "meaning": "Sales Revenue",
        "legacy_code": "4100",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SALES_RETURNS: {
        "meaning": "Sales Returns",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SALES_DISCOUNT: {
        "meaning": "Sales Discount",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_VAT_INPUT: {
        "meaning": "VAT Input",
        "legacy_code": "2122",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_VAT_OUTPUT: {
        "meaning": "VAT Output",
        "legacy_code": "2121",
        "required": True,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_FX_GAIN: {
        "meaning": "Foreign Exchange Gain",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_FX_LOSS: {
        "meaning": "Foreign Exchange Loss",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_CHEQUES_UNDER_COLLECTION: {
        "meaning": "Cheques Under Collection",
        "legacy_code": "1150",
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN: {
        "meaning": "Inventory Adjustment Gain",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS: {
        "meaning": "Inventory Adjustment Loss",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_FREIGHT_IN: {
        "meaning": "Freight In",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_CUSTOMS_DUTY: {
        "meaning": "Customs Duty",
        "legacy_code": None,
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE: {
        "meaning": "Deferred Cheques Payable",
        "legacy_code": "2130",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PARTNER_CURRENT_ACCOUNT: {
        "meaning": "Partner Current Account",
        "legacy_code": "3350",
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT: {
        "meaning": "Merchant Current Account",
        "legacy_code": "2115",
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SHIPPING_REVENUE: {
        "meaning": "Shipping Revenue",
        "legacy_code": "4300",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_MISC_EXPENSE: {
        "meaning": "Miscellaneous Expense",
        "legacy_code": "6990",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_COMMISSION_EXPENSE: {
        "meaning": "Commission Expense",
        "legacy_code": "6150",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_EMPLOYEE_ADVANCES: {
        "meaning": "Employee Advances",
        "legacy_code": "1160",
        "required": False,
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PAYROLL_EXPENSE: {
        "meaning": "Payroll Expense",
        "legacy_code": "6100",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PAYROLL_EXPENSE_2: {
        "meaning": "Payroll Expense (Alternative)",
        "legacy_code": "6220",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PAYROLL_PAYABLE: {
        "meaning": "Payroll Payable",
        "legacy_code": "2140",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_BANK_FEES: {
        "meaning": "Bank Fees",
        "legacy_code": "6950",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_BANK_INTEREST_INCOME: {
        "meaning": "Bank Interest Income",
        "legacy_code": "4500",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_DONATION_REVENUE: {
        "meaning": "Donation Revenue",
        "legacy_code": "4200",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_FIXED_ASSET_ASSET: {
        "meaning": "Fixed Asset Asset",
        "legacy_code": "1240",
        "required": False,
        "resolution_mode": RESOLUTION_MODE_RECORD,
    },
    GL_CONCEPT_DEPRECIATION_EXPENSE: {
        "meaning": "Depreciation Expense",
        "legacy_code": "6180",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_RECORD,
    },
    GL_CONCEPT_ACCUMULATED_DEPRECIATION: {
        "meaning": "Accumulated Depreciation",
        "legacy_code": "1290",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_RECORD,
    },
    GL_CONCEPT_FIXED_ASSET_GAIN: {
        "meaning": "Fixed Asset Disposal Gain",
        "legacy_code": "4500",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_FIXED_ASSET_LOSS: {
        "meaning": "Fixed Asset Disposal Loss",
        "legacy_code": "6990",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SHOP_SALES_REVENUE: {
        "meaning": "Online Store Sales Revenue",
        "legacy_code": "4103",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_COUPON_EXPENSE: {
        "meaning": "Store Coupon Discount Expense",
        "legacy_code": "6130",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_LOYALTY_LIABILITY: {
        "meaning": "Customer Loyalty Points Liability",
        "legacy_code": "2160",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SHIPPING_COST_EXPENSE: {
        "meaning": "Shipping Cost Expense",
        "legacy_code": "6140",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_CAMPAIGN_DISCOUNT_EXPENSE: {
        "meaning": "Campaign Discount Expense",
        "legacy_code": "6131",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_WARRANTY_CLAIM_EXPENSE: {
        "meaning": "Warranty Claim Expense",
        "legacy_code": "6400",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PURCHASE_RETURNS: {
        "meaning": "Purchase Returns",
        "legacy_code": None,
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SALES_COMMISSION: {
        "meaning": "Sales Representative Commission",
        "legacy_code": "6120",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_TIER_DISCOUNT: {
        "meaning": "Price Tier Discount",
        "legacy_code": None,
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_CARD_PROCESSING_FEES: {
        "meaning": "Card Processing Fees",
        "legacy_code": "6260",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_PURCHASES: {
        "meaning": "Purchases",
        "legacy_code": None,
        "required": True,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_LANDED_COST: {
        "meaning": "Landed Cost Allocation",
        "legacy_code": "5300",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_NON_POSTING,
    },
    GL_CONCEPT_FOOD_SALES_REVENUE: {
        "meaning": "Food Sales Revenue",
        "legacy_code": "4114",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_BEVERAGE_SALES_REVENUE: {
        "meaning": "Beverage Sales Revenue",
        "legacy_code": "4115",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_POS_CASH_DIFFERENCE: {
        "meaning": "POS Cash Difference",
        "legacy_code": None,
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AZAD_PLATFORM_PAYABLE: {
        "meaning": "Azad Platform Fee Payable",
        "legacy_code": "2180",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AZAD_PLATFORM_FEE_ACCRUED: {
        "meaning": "Azad Platform Fee Accrued",
        "legacy_code": "2181",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AZAD_PLATFORM_FEE_PAID: {
        "meaning": "Azad Platform Fee Paid",
        "legacy_code": "2182",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AZAD_SUBSCRIPTION_EXPENSE: {
        "meaning": "Azad Subscription Expense",
        "legacy_code": "6410",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_AZAD_SUBSCRIPTION_REVENUE: {
        "meaning": "Azad Subscription Revenue",
        "legacy_code": "4700",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_OPENING_BALANCE_EQUITY: {
        "meaning": "Opening Balance Equity",
        "legacy_code": "3130",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_ACCOUNTS_PAYABLE: {
        "meaning": "Accounts Payable (Legacy)",
        "legacy_code": "2110",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_END_OF_SERVICE_PROVISION: {
        "meaning": "End of Service Provision Expense",
        "legacy_code": "6190",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_END_OF_SERVICE_LIABILITY: {
        "meaning": "End of Service Benefits Provision",
        "legacy_code": "2140",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_LEAVE_ACCRUAL_LIABILITY: {
        "meaning": "Leave Accrual Liability",
        "legacy_code": "2160",
        "required": False,
        "normal_balance": "credit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
    GL_CONCEPT_SUSPENSE: {
        "meaning": "Suspense Account",
        "legacy_code": "2999",
        "required": False,
        "normal_balance": "debit",
        "resolution_mode": RESOLUTION_MODE_MAPPING,
    },
}

VALID_GL_CONCEPT_CODES = frozenset(GL_CONCEPT_CODES)
REQUIRED_GL_CONCEPTS = frozenset(
    code for code, meta in GL_CONCEPT_REGISTRY.items() if meta["required"]
)

_GL_CONCEPT_CODE_CHECK = "concept_code IN ({})".format(
    ", ".join(f"'{code}'" for code in GL_CONCEPT_CODES)
)
