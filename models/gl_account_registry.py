"""
Declarative GL Account Registry.
Maps system modules and industries to required GL account templates.
This module never touches the database — it is pure configuration.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GLAccountTemplate:
    code: str
    name: str
    name_ar: str
    type: str
    level: int = 0
    is_header: bool = False
    parent_code: Optional[str] = None
    industry_code: Optional[str] = None
    module_code: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class GLConceptMappingTemplate:
    concept_code: str
    account_code: str
    module_code: str


@dataclass(frozen=True)
class GLModuleDefinition:
    module_code: str
    required: bool
    feature_flag: Optional[str] = None
    accounts: list = field(default_factory=list)
    mappings: list = field(default_factory=list)


@dataclass(frozen=True)
class GLIndustryExtension:
    industry_code: str
    display_name_ar: str
    display_name_en: str
    accounts: list = field(default_factory=list)


BASE_ACCOUNTS = [
    GLAccountTemplate('1000', 'Assets', 'الأصول', 'asset', 0, True),
    GLAccountTemplate('1100', 'Current Assets', 'أصول متداولة', 'asset', 1, True, '1000'),
    GLAccountTemplate('1110', 'Cash and Cash Equivalents', 'النقد وما في حكمه', 'asset', 2, True, '1100'),
    GLAccountTemplate('1111', 'Cash Box (Main)', 'الصندوق الرئيسي', 'asset', 3, False, '1110'),
    GLAccountTemplate('1112', 'Cash Box (Branch)', 'صندوق الفرع', 'asset', 3, False, '1110'),
    GLAccountTemplate('1120', 'Bank Accounts', 'الحسابات البنكية', 'asset', 2, True, '1100'),
    GLAccountTemplate('1130', 'Accounts Receivable', 'العملاء (ذمم مدينة)', 'asset', 2, False, '1100'),
    GLAccountTemplate('1131', 'AR - Trade Customers', 'عملاء التجارة', 'asset', 3, False, '1130'),
    GLAccountTemplate('1132', 'AR - Partners', 'عملاء الشراكة', 'asset', 3, False, '1130'),
    GLAccountTemplate('1133', 'AR - Staff', 'ذمم الموظفين', 'asset', 3, False, '1130'),
    GLAccountTemplate('1140', 'Inventory', 'المخزون', 'asset', 2, False, '1100'),
    GLAccountTemplate('1141', 'Inventory - Finished Goods', 'مخزون بضاعة جاهزة', 'asset', 3, False, '1140'),
    GLAccountTemplate('1142', 'Inventory - Raw Materials', 'مخزون مواد أولية', 'asset', 3, False, '1140'),
    GLAccountTemplate('1143', 'Inventory - Spare Parts', 'مخزون قطع غيار', 'asset', 3, False, '1140'),
    GLAccountTemplate('1150', 'Cheques Under Collection', 'شيكات برسم التحصيل', 'asset', 2, False, '1100'),
    GLAccountTemplate('1160', 'Prepayments', 'مدفوعات مقدمة', 'asset', 2, False, '1100'),
    GLAccountTemplate('1170', 'Employee Advances', 'سلف الموظفين', 'asset', 2, False, '1100'),
    GLAccountTemplate('1180', 'Fixed Assets', 'الأصول الثابتة', 'asset', 2, True, '1100'),
    GLAccountTemplate('1190', 'Accumulated Depreciation', 'مجمع الإهلاك', 'asset', 2, False, '1100'),
    GLAccountTemplate('1200', 'Non-Current Assets', 'أصول غير متداولة', 'asset', 1, True, '1000'),
    GLAccountTemplate('2000', 'Liabilities', 'الخصوم', 'liability', 0, True),
    GLAccountTemplate('2100', 'Current Liabilities', 'خصوم متداولة', 'liability', 1, True, '2000'),
    GLAccountTemplate('2110', 'Accounts Payable', 'الموردين (ذمم دائنة)', 'liability', 2, False, '2100'),
    GLAccountTemplate('2111', 'AP - Suppliers', 'موردين', 'liability', 3, False, '2110'),
    GLAccountTemplate('2112', 'AP - Trade Payables', 'ذمم دائنة تجارية', 'liability', 3, False, '2110'),
    GLAccountTemplate('2120', 'VAT Payable', 'ضريبة القيمة المضافة', 'liability', 2, False, '2100'),
    GLAccountTemplate('2121', 'VAT Output', 'ضريبة مخرجات', 'liability', 3, False, '2120'),
    GLAccountTemplate('2122', 'VAT Input', 'ضريبة مدخلات', 'liability', 3, False, '2120'),
    GLAccountTemplate('2130', 'Deferred Cheques Payable', 'شيكات برسم الدفع', 'liability', 2, False, '2100'),
    GLAccountTemplate('2140', 'Payroll Payable', 'رواتب مستحقة', 'liability', 2, False, '2100'),
    GLAccountTemplate('2150', 'Partner Current Accounts', 'حسابات الشركاء الجارية', 'liability', 2, False, '2100'),
    GLAccountTemplate('2151', 'Partner - Merchant Account', 'حساب التاجر', 'liability', 3, False, '2150'),
    GLAccountTemplate('2152', 'Partner - Commission Hold', 'عمولات محتجزة', 'liability', 3, False, '2150'),
    GLAccountTemplate('2160', 'Loyalty Points Liability', 'التزام نقاط الولاء', 'liability', 2, False, '2100'),
    GLAccountTemplate('2170', 'Customer Deposits', 'عربون العملاء', 'liability', 2, False, '2100'),
    GLAccountTemplate('2180', 'Azad Platform Payable', 'ذمم دائنة - منصة أزاد', 'liability', 2, False, '2100'),
    GLAccountTemplate('2181', 'Azad Platform Fee Accrued', 'رسوم منصة متراكمة', 'liability', 3, False, '2180'),
    GLAccountTemplate('2182', 'Azad Platform Fee Paid', 'رسوم منصة مدفوعة', 'liability', 3, False, '2180'),
    GLAccountTemplate('2200', 'Non-Current Liabilities', 'خصوم غير متداولة', 'liability', 1, True, '2000'),
    GLAccountTemplate('3000', 'Equity', 'حقوق الملكية', 'equity', 0, True),
    GLAccountTemplate('3100', 'Capital', 'رأس المال', 'equity', 1, False, '3000'),
    GLAccountTemplate('3200', 'Retained Earnings', 'أرباح مرحلة', 'equity', 1, False, '3000'),
    GLAccountTemplate('3300', 'Owner Drawings', 'مسحوبات المالك', 'equity', 1, False, '3000'),
    GLAccountTemplate('4000', 'Revenue', 'الإيرادات', 'revenue', 0, True),
    GLAccountTemplate('4100', 'Sales Revenue', 'إيرادات المبيعات', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4101', 'Sales - Retail', 'مبيعات التجزئة', 'revenue', 2, False, '4100'),
    GLAccountTemplate('4102', 'Sales - Wholesale', 'مبيعات الجملة', 'revenue', 2, False, '4100'),
    GLAccountTemplate('4103', 'Sales - Online Store', 'مبيعات المتجر الإلكتروني', 'revenue', 2, False, '4100'),
    GLAccountTemplate('4104', 'Sales - Services', 'إيرادات الخدمات', 'revenue', 2, False, '4100'),
    GLAccountTemplate('4200', 'Shipping Revenue', 'إيرادات الشحن', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4300', 'Other Revenue', 'إيرادات أخرى', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4400', 'FX Gains', 'أرباح صرف العملات', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4500', 'Donation Revenue', 'إيرادات التبرعات', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4600', 'Fixed Asset Disposal Gain', 'أرباح بيع الأصول', 'revenue', 1, False, '4000'),
    GLAccountTemplate('4700', 'Azad Subscription Revenue', 'إيرادات اشتراك أزاد', 'revenue', 1, False, '4000'),
    GLAccountTemplate('5000', 'Cost of Sales', 'تكلفة المبيعات', 'expense', 0, True),
    GLAccountTemplate('5100', 'Cost of Goods Sold', 'تكلفة البضاعة المباعة', 'expense', 1, False, '5000'),
    GLAccountTemplate('5101', 'COGS - Retail', 'تكلفة بضاعة تجزئة', 'expense', 2, False, '5100'),
    GLAccountTemplate('5102', 'COGS - Wholesale', 'تكلفة بضاعة جملة', 'expense', 2, False, '5100'),
    GLAccountTemplate('5103', 'COGS - Online', 'تكلفة بضاعة أونلاين', 'expense', 2, False, '5100'),
    GLAccountTemplate('5200', 'Inventory Adjustments', 'تسويات المخزون', 'expense', 1, True, '5000'),
    GLAccountTemplate('5201', 'Inventory Gain', 'ربح مخزوني', 'expense', 2, False, '5200'),
    GLAccountTemplate('5202', 'Inventory Loss', 'خسارة مخزونية', 'expense', 2, False, '5200'),
    GLAccountTemplate('5300', 'Landed Costs', 'تكاليف الشحن والجمارك', 'expense', 1, True, '5000'),
    GLAccountTemplate('5301', 'Freight In', 'شحن وارد', 'expense', 2, False, '5300'),
    GLAccountTemplate('5302', 'Customs Duty', 'رسوم جمركية', 'expense', 2, False, '5300'),
    GLAccountTemplate('5303', 'Insurance In', 'تأمين وارد', 'expense', 2, False, '5300'),
    GLAccountTemplate('6000', 'Operating Expenses', 'مصروفات تشغيلية', 'expense', 0, True),
    GLAccountTemplate('6100', 'Sales & Marketing Expenses', 'مصروفات تسويق ومبيعات', 'expense', 1, True, '6000'),
    GLAccountTemplate('6110', 'Advertising & Marketing', 'إعلان وتسويق', 'expense', 2, False, '6100'),
    GLAccountTemplate('6120', 'Sales Commissions', 'عمولات المبيعات', 'expense', 2, False, '6100'),
    GLAccountTemplate('6130', 'Store Discounts & Coupons', 'خصومات وكوبونات', 'expense', 2, False, '6100'),
    GLAccountTemplate('6131', 'Campaign Discounts', 'خصومات الحملات', 'expense', 2, False, '6100'),
    GLAccountTemplate('6140', 'Shipping & Delivery Cost', 'تكلفة الشحن والتوصيل', 'expense', 2, False, '6100'),
    GLAccountTemplate('6200', 'Administrative Expenses', 'مصروفات إدارية', 'expense', 1, True, '6000'),
    GLAccountTemplate('6210', 'Rent', 'الإيجار', 'expense', 2, False, '6200'),
    GLAccountTemplate('6220', 'Salaries & Wages', 'الرواتب والأجور', 'expense', 2, False, '6200'),
    GLAccountTemplate('6230', 'Utilities', 'الكهرباء والمياه', 'expense', 2, False, '6200'),
    GLAccountTemplate('6240', 'Maintenance & Repairs', 'صيانة وإصلاحات', 'expense', 2, False, '6200'),
    GLAccountTemplate('6250', 'Office Supplies', 'قرطاسية ومستلزمات', 'expense', 2, False, '6200'),
    GLAccountTemplate('6260', 'Bank Fees & Charges', 'رسوم بنكية', 'expense', 2, False, '6200'),
    GLAccountTemplate('6270', 'Insurance', 'تأمين', 'expense', 2, False, '6200'),
    GLAccountTemplate('6280', 'Legal & Professional Fees', 'رسوم قانونية', 'expense', 2, False, '6200'),
    GLAccountTemplate('6290', 'Communication', 'اتصالات', 'expense', 2, False, '6200'),
    GLAccountTemplate('6300', 'Depreciation Expense', 'مصروف الإهلاك', 'expense', 1, False, '6000'),
    GLAccountTemplate('6400', 'Warranty Claims', 'مطالبات الضمان', 'expense', 1, False, '6000'),
    GLAccountTemplate('6410', 'Platform Subscription Expense', 'مصروف اشتراك المنصة', 'expense', 2, False, '6000'),
    GLAccountTemplate('6500', 'Miscellaneous Expenses', 'مصروفات متنوعة', 'expense', 1, False, '6000'),
    GLAccountTemplate('6600', 'FX Losses', 'خسائر صرف العملات', 'expense', 1, False, '6000'),
    GLAccountTemplate('6700', 'Fixed Asset Disposal Loss', 'خسائر بيع الأصول', 'expense', 1, False, '6000'),
]

INDUSTRY_EXTENSIONS = {
    'automotive': [
        GLAccountTemplate('4105', 'Service Revenue', 'إيرادات الخدمات', 'revenue', 2, False, '4100', 'automotive'),
        GLAccountTemplate('5104', 'COGS - Services', 'تكلفة خدمات', 'expense', 2, False, '5100', 'automotive'),
        GLAccountTemplate('6241', 'Workshop Equipment', 'معدات الورشة', 'expense', 2, False, '6200', 'automotive'),
    ],
    'supermarket': [
        GLAccountTemplate('1144', 'Inventory - Perishable Goods', 'مخزون بضاعة سريعة التلف', 'asset', 3, False, '1140', 'supermarket'),
        GLAccountTemplate('1145', 'Inventory - Packaged Goods', 'مخزون بضاعة معبأة', 'asset', 3, False, '1140', 'supermarket'),
        GLAccountTemplate('4106', 'Fresh Sales', 'مبيعات طازجة', 'revenue', 2, False, '4100', 'supermarket'),
        GLAccountTemplate('5203', 'Expiry Loss', 'خسارة انتهاء الصلاحية', 'expense', 2, False, '5200', 'supermarket'),
    ],
    'pharmacy': [
        GLAccountTemplate('1146', 'Inventory - Prescription', 'مخزون أدوية بوصفة', 'asset', 3, False, '1140', 'pharmacy'),
        GLAccountTemplate('1147', 'Inventory - OTC', 'مخزون أدوية بدون وصفة', 'asset', 3, False, '1140', 'pharmacy'),
        GLAccountTemplate('4107', 'Prescription Sales', 'مبيعات بوصفة', 'revenue', 2, False, '4100', 'pharmacy'),
        GLAccountTemplate('5105', 'COGS - Prescription', 'تكلفة أدوية بوصفة', 'expense', 2, False, '5100', 'pharmacy'),
    ],
    'electronics': [
        GLAccountTemplate('1148', 'Inventory - Devices', 'مخزون أجهزة', 'asset', 3, False, '1140', 'electronics'),
        GLAccountTemplate('4108', 'Device Sales', 'مبيعات أجهزة', 'revenue', 2, False, '4100', 'electronics'),
        GLAccountTemplate('6121', 'Device Warranty Expense', 'مصروف ضمان أجهزة', 'expense', 2, False, '6100', 'electronics'),
    ],
    'mobile_new': [
        GLAccountTemplate('1149', 'Inventory - Mobile Phones', 'مخزون موبايلات جديدة', 'asset', 3, False, '1140', 'mobile_new'),
        GLAccountTemplate('4109', 'Mobile Sales', 'مبيعات موبايلات', 'revenue', 2, False, '4100', 'mobile_new'),
        GLAccountTemplate('6122', 'IMEI Registration Cost', 'تكلفة تسجيل IMEI', 'expense', 2, False, '6100', 'mobile_new'),
    ],
    'mobile_used': [
        GLAccountTemplate('1151', 'Inventory - Used Mobile', 'مخزون موبايلات مستعملة', 'asset', 3, False, '1140', 'mobile_used'),
        GLAccountTemplate('4110', 'Used Mobile Sales', 'مبيعات موبايلات مستعملة', 'revenue', 2, False, '4100', 'mobile_used'),
        GLAccountTemplate('5204', 'Refurbishment Cost', 'تكلفة تجديد', 'expense', 2, False, '5200', 'mobile_used'),
    ],
    'mobile_parts': [
        GLAccountTemplate('1152', 'Inventory - Spare Parts Mobile', 'مخزون قطع غيار موبايلات', 'asset', 3, False, '1140', 'mobile_parts'),
        GLAccountTemplate('4111', 'Parts Sales', 'مبيعات قطع غيار', 'revenue', 2, False, '4100', 'mobile_parts'),
        GLAccountTemplate('5106', 'COGS - Parts', 'تكلفة قطع غيار', 'expense', 2, False, '5100', 'mobile_parts'),
    ],
    'batteries': [
        GLAccountTemplate('1153', 'Inventory - Batteries', 'مخزون بطاريات', 'asset', 3, False, '1140', 'batteries'),
        GLAccountTemplate('4112', 'Battery Sales', 'مبيعات بطاريات', 'revenue', 2, False, '4100', 'batteries'),
        GLAccountTemplate('5107', 'COGS - Batteries', 'تكلفة بطاريات', 'expense', 2, False, '5100', 'batteries'),
        GLAccountTemplate('6242', 'Battery Recycling', 'إعادة تدوير بطاريات', 'expense', 2, False, '6200', 'batteries'),
    ],
    'clothing': [
        GLAccountTemplate('1154', 'Inventory - Clothing', 'مخزون ملابس', 'asset', 3, False, '1140', 'clothing'),
        GLAccountTemplate('4113', 'Clothing Sales', 'مبيعات ملابس', 'revenue', 2, False, '4100', 'clothing'),
        GLAccountTemplate('5108', 'COGS - Clothing', 'تكلفة ملابس', 'expense', 2, False, '5100', 'clothing'),
        GLAccountTemplate('6123', 'Seasonal Clearance', 'تصفية موسمية', 'expense', 2, False, '6100', 'clothing'),
    ],
    'restaurant': [
        GLAccountTemplate('1155', 'Inventory - Food', 'مخزون طعام', 'asset', 3, False, '1140', 'restaurant'),
        GLAccountTemplate('1156', 'Inventory - Beverage', 'مخزون مشروبات', 'asset', 3, False, '1140', 'restaurant'),
        GLAccountTemplate('4114', 'Food Sales', 'مبيعات طعام', 'revenue', 2, False, '4100', 'restaurant'),
        GLAccountTemplate('4115', 'Beverage Sales', 'مبيعات مشروبات', 'revenue', 2, False, '4100', 'restaurant'),
        GLAccountTemplate('5109', 'COGS - Food', 'تكلفة طعام', 'expense', 2, False, '5100', 'restaurant'),
    ],
    'construction': [
        GLAccountTemplate('1157', 'Inventory - Materials', 'مخزون مواد بناء', 'asset', 3, False, '1140', 'construction'),
        GLAccountTemplate('1158', 'Equipment Rental', 'تأجير معدات', 'asset', 3, False, '1140', 'construction'),
        GLAccountTemplate('4116', 'Contract Revenue', 'إيرادات عقود', 'revenue', 2, False, '4100', 'construction'),
        GLAccountTemplate('5110', 'COGS - Materials', 'تكلفة مواد بناء', 'expense', 2, False, '5100', 'construction'),
        GLAccountTemplate('6243', 'Site Expenses', 'مصروفات موقع', 'expense', 2, False, '6200', 'construction'),
    ],
    'jewelry': [
        GLAccountTemplate('1159', 'Inventory - Gold', 'مخزون ذهب', 'asset', 3, False, '1140', 'jewelry'),
        GLAccountTemplate('1162', 'Inventory - Gemstones', 'مخزون أحجار كريمة', 'asset', 3, False, '1140', 'jewelry'),
        GLAccountTemplate('4117', 'Jewelry Sales', 'مبيعات مجوهرات', 'revenue', 2, False, '4100', 'jewelry'),
        GLAccountTemplate('5111', 'COGS - Gold', 'تكلفة ذهب', 'expense', 2, False, '5100', 'jewelry'),
        GLAccountTemplate('6244', 'Security Cost', 'تكلفة أمن', 'expense', 2, False, '6200', 'jewelry'),
    ],
    'trading': [
        GLAccountTemplate('1161', 'Inventory - General Trading', 'مخزون تجارة عامة', 'asset', 3, False, '1140', 'trading'),
        GLAccountTemplate('4118', 'Trading Revenue', 'إيرادات تجارة', 'revenue', 2, False, '4100', 'trading'),
        GLAccountTemplate('5112', 'COGS - Trading', 'تكلفة تجارة', 'expense', 2, False, '5100', 'trading'),
    ],
}

GL_MODULE_DEFINITIONS = {
    'core_sales': GLModuleDefinition(
        'core_sales', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('SALES_REVENUE', '4100', 'core_sales'),
            GLConceptMappingTemplate('SALES_RETURNS', '4100', 'core_sales'),
            GLConceptMappingTemplate('SALES_DISCOUNT', '4100', 'core_sales'),
            GLConceptMappingTemplate('SALES_COMMISSION', '6120', 'core_sales'),
            GLConceptMappingTemplate('TIER_DISCOUNT', '4100', 'core_sales'),
            GLConceptMappingTemplate('AR', '1130', 'core_sales'),
        ],
    ),
    'core_purchases': GLModuleDefinition(
        'core_purchases', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('AP', '2110', 'core_purchases'),
            GLConceptMappingTemplate('PURCHASE_RETURNS', '2110', 'core_purchases'),
            GLConceptMappingTemplate('INVENTORY_ASSET', '1140', 'core_purchases'),
            GLConceptMappingTemplate('COGS', '5100', 'core_purchases'),
            GLConceptMappingTemplate('FREIGHT_IN', '5301', 'core_purchases'),
            GLConceptMappingTemplate('CUSTOMS_DUTY', '5302', 'core_purchases'),
            GLConceptMappingTemplate('LANDED_COST', '5300', 'core_purchases'),
        ],
    ),
    'core_payments': GLModuleDefinition(
        'core_payments', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('CASH', '1111', 'core_payments'),
            GLConceptMappingTemplate('BANK', '1120', 'core_payments'),
            GLConceptMappingTemplate('CHEQUES_UNDER_COLLECTION', '1150', 'core_payments'),
            GLConceptMappingTemplate('DEFERRED_CHEQUES_PAYABLE', '2130', 'core_payments'),
            GLConceptMappingTemplate('BANK_FEES', '6260', 'core_payments'),
            GLConceptMappingTemplate('CARD_PROCESSING_FEES', '6260', 'core_payments'),
        ],
    ),
    'core_inventory': GLModuleDefinition(
        'core_inventory', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('INVENTORY_ASSET', '1140', 'core_inventory'),
            GLConceptMappingTemplate('COGS', '5100', 'core_inventory'),
            GLConceptMappingTemplate('COGS_REVERSAL', '5100', 'core_inventory'),
            GLConceptMappingTemplate('INVENTORY_ADJUSTMENT_GAIN', '5201', 'core_inventory'),
            GLConceptMappingTemplate('INVENTORY_ADJUSTMENT_LOSS', '5202', 'core_inventory'),
        ],
    ),
    'shop_online': GLModuleDefinition(
        'shop_online', False, 'enable_online_store',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('SHOP_SALES_REVENUE', '4103', 'shop_online'),
            GLConceptMappingTemplate('COUPON_EXPENSE', '6130', 'shop_online'),
            GLConceptMappingTemplate('LOYALTY_LIABILITY', '2160', 'shop_online'),
        ],
    ),
    'shipments': GLModuleDefinition(
        'shipments', False, 'enable_shipments',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('SHIPPING_REVENUE', '4200', 'shipments'),
            GLConceptMappingTemplate('SHIPPING_COST_EXPENSE', '6140', 'shipments'),
        ],
    ),
    'campaigns': GLModuleDefinition(
        'campaigns', False, 'enable_campaigns',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('CAMPAIGN_DISCOUNT_EXPENSE', '6131', 'campaigns'),
        ],
    ),
    'partners': GLModuleDefinition(
        'partners', False, 'enable_partners',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('PARTNER_CURRENT_ACCOUNT', '2150', 'partners'),
            GLConceptMappingTemplate('MERCHANT_CURRENT_ACCOUNT', '2151', 'partners'),
            GLConceptMappingTemplate('COMMISSION_EXPENSE', '6120', 'partners'),
        ],
    ),
    'payroll': GLModuleDefinition(
        'payroll', False, 'enable_payroll',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('PAYROLL_EXPENSE', '6220', 'payroll'),
            GLConceptMappingTemplate('PAYROLL_PAYABLE', '2140', 'payroll'),
            GLConceptMappingTemplate('EMPLOYEE_ADVANCES', '1170', 'payroll'),
        ],
    ),
    'fixed_assets': GLModuleDefinition(
        'fixed_assets', False, 'enable_fixed_assets',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('FIXED_ASSET_ASSET', '1180', 'fixed_assets'),
            GLConceptMappingTemplate('DEPRECIATION_EXPENSE', '6300', 'fixed_assets'),
            GLConceptMappingTemplate('ACCUMULATED_DEPRECIATION', '1190', 'fixed_assets'),
            GLConceptMappingTemplate('FIXED_ASSET_GAIN', '4600', 'fixed_assets'),
            GLConceptMappingTemplate('FIXED_ASSET_LOSS', '6700', 'fixed_assets'),
        ],
    ),
    'donations': GLModuleDefinition(
        'donations', False, 'enable_donations',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('DONATION_REVENUE', '4500', 'donations'),
        ],
    ),
    'currency_fx': GLModuleDefinition(
        'currency_fx', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('FX_GAIN', '4400', 'currency_fx'),
            GLConceptMappingTemplate('FX_LOSS', '6600', 'currency_fx'),
        ],
    ),
    'vat': GLModuleDefinition(
        'vat', True,
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('VAT_INPUT', '2122', 'vat'),
            GLConceptMappingTemplate('VAT_OUTPUT', '2121', 'vat'),
        ],
    ),
    'warranty': GLModuleDefinition(
        'warranty', False, 'enable_warranty_tracking',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('WARRANTY_CLAIM_EXPENSE', '6400', 'warranty'),
        ],
    ),
    'bank_reconciliation': GLModuleDefinition(
        'bank_reconciliation', False, 'enable_bank_reconciliation',
        accounts=[],
        mappings=[
            GLConceptMappingTemplate('BANK_INTEREST_INCOME', '4300', 'bank_reconciliation'),
        ],
    ),
    'azad_platform': GLModuleDefinition(
        'azad_platform', False, 'enable_ecommerce',
        accounts=[
            GLAccountTemplate('2180', 'Azad Platform Payable', 'ذمم دائنة - منصة أزاد', 'liability', 2, False, '2100'),
            GLAccountTemplate('2181', 'Azad Platform Fee Accrued', 'رسوم منصة متراكمة', 'liability', 3, False, '2180'),
            GLAccountTemplate('2182', 'Azad Platform Fee Paid', 'رسوم منصة مدفوعة', 'liability', 3, False, '2180'),
        ],
        mappings=[
            GLConceptMappingTemplate('AZAD_PLATFORM_PAYABLE', '2180', 'azad_platform'),
            GLConceptMappingTemplate('AZAD_PLATFORM_FEE_ACCRUED', '2181', 'azad_platform'),
            GLConceptMappingTemplate('AZAD_PLATFORM_FEE_PAID', '2182', 'azad_platform'),
            GLConceptMappingTemplate('AZAD_SUBSCRIPTION_EXPENSE', '6410', 'azad_platform'),
            GLConceptMappingTemplate('AZAD_SUBSCRIPTION_REVENUE', '4700', 'azad_platform'),
        ],
    ),
}

VALID_INDUSTRY_CODES = frozenset(INDUSTRY_EXTENSIONS.keys())
VALID_INDUSTRY_CODES = VALID_INDUSTRY_CODES | {'general'}
