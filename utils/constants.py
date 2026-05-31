CUSTOMER_TYPES = [
    ('regular', {'ar': 'عادي', 'en': 'Regular'}),
    ('merchant', {'ar': 'تاجر', 'en': 'Merchant'}),
    ('partner', {'ar': 'شريك', 'en': 'Partner'}),
]

CUSTOMER_CLASSIFICATIONS = [
    ('vip', {'ar': 'VIP - عميل مميز', 'en': 'VIP', 'threshold': 100000}),
    ('premium', {'ar': 'ممتاز', 'en': 'Premium', 'threshold': 50000}),
    ('regular', {'ar': 'عادي', 'en': 'Regular', 'threshold': 0}),
    ('inactive', {'ar': 'غير نشط', 'en': 'Inactive', 'threshold': 0}),
]

PAYMENT_METHODS = [
    ('cash', {'ar': 'نقدي', 'en': 'Cash'}),
    ('card', {'ar': 'بطاقة', 'en': 'Card'}),
    ('bank_transfer', {'ar': 'تحويل بنكي', 'en': 'Bank Transfer'}),
    ('cheque', {'ar': 'شيك', 'en': 'Cheque'}),
    ('e_wallet', {'ar': 'محفظة إلكترونية', 'en': 'E-Wallet'}),
]

PAYMENT_STATUSES = [
    ('paid', {'ar': 'مدفوع', 'en': 'Paid'}),
    ('partial', {'ar': 'جزئي', 'en': 'Partial'}),
    ('unpaid', {'ar': 'غير مدفوع', 'en': 'Unpaid'}),
]

SALE_STATUSES = [
    ('confirmed', {'ar': 'مؤكدة', 'en': 'Confirmed'}),
    ('cancelled', {'ar': 'ملغاة', 'en': 'Cancelled'}),
]

PURCHASE_STATUSES = [
    ('confirmed', {'ar': 'مؤكدة', 'en': 'Confirmed'}),
    ('cancelled', {'ar': 'ملغاة', 'en': 'Cancelled'}),
]

STOCK_MOVEMENT_TYPES = [
    ('purchase', {'ar': 'شراء', 'en': 'Purchase'}),
    ('sale', {'ar': 'بيع', 'en': 'Sale'}),
    ('adjustment', {'ar': 'تسوية', 'en': 'Adjustment'}),
    ('return', {'ar': 'إرجاع', 'en': 'Return'}),
    ('damage', {'ar': 'تالف', 'en': 'Damage'}),
]

USER_ROLES = [
    ('owner', {'ar': 'المالك', 'en': 'Owner'}),
    ('super_admin', {'ar': 'مدير عام', 'en': 'Super Admin'}),
    ('manager', {'ar': 'مدير الشركة', 'en': 'Manager'}),
    ('branch_manager', {'ar': 'مدير الفرع', 'en': 'Branch Manager'}),
    ('accountant', {'ar': 'محاسب', 'en': 'Accountant'}),
    ('seller', {'ar': 'بائع', 'en': 'Seller'}),
    ('developer', {'ar': 'مطوّر', 'en': 'Developer'}),
]

CURRENCIES = [
    ('AED', {'ar': 'درهم إماراتي', 'en': 'UAE Dirham', 'symbol': 'د.إ'}),
    ('USD', {'ar': 'دولار أمريكي', 'en': 'US Dollar', 'symbol': '$'}),
    ('EUR', {'ar': 'يورو', 'en': 'Euro', 'symbol': '€'}),
    ('GBP', {'ar': 'جنيه إسترليني', 'en': 'British Pound', 'symbol': '£'}),
    ('SAR', {'ar': 'ريال سعودي', 'en': 'Saudi Riyal', 'symbol': 'ر.س'}),
    ('KWD', {'ar': 'دينار كويتي', 'en': 'Kuwaiti Dinar', 'symbol': 'د.ك'}),
    ('QAR', {'ar': 'ريال قطري', 'en': 'Qatari Riyal', 'symbol': 'ر.ق'}),
    ('OMR', {'ar': 'ريال عماني', 'en': 'Omani Rial', 'symbol': 'ر.ع'}),
    ('BHD', {'ar': 'دينار بحريني', 'en': 'Bahraini Dinar', 'symbol': 'د.ب'}),
]

PRODUCT_UNITS = [
    ('piece', {'ar': 'قطعة', 'en': 'Piece'}),
    ('kg', {'ar': 'كيلوجرام', 'en': 'Kilogram'}),
    ('liter', {'ar': 'لتر', 'en': 'Liter'}),
    ('meter', {'ar': 'متر', 'en': 'Meter'}),
    ('box', {'ar': 'صندوق', 'en': 'Box'}),
    ('set', {'ar': 'مجموعة', 'en': 'Set'}),
]

COUNTRIES = [
    ('AE', {'ar': 'الإمارات', 'en': 'UAE'}),
    ('SA', {'ar': 'السعودية', 'en': 'Saudi Arabia'}),
    ('DE', {'ar': 'ألمانيا', 'en': 'Germany'}),
    ('JP', {'ar': 'اليابان', 'en': 'Japan'}),
    ('US', {'ar': 'أمريكا', 'en': 'USA'}),
    ('KR', {'ar': 'كوريا', 'en': 'South Korea'}),
    ('CN', {'ar': 'الصين', 'en': 'China'}),
    ('IT', {'ar': 'إيطاليا', 'en': 'Italy'}),
    ('FR', {'ar': 'فرنسا', 'en': 'France'}),
    ('GB', {'ar': 'بريطانيا', 'en': 'United Kingdom'}),
]

# مصدر واحد لرموز الصلاحيات (Backend + Frontend)
PERMISSION_CODES = [
    'manage_sales', 'manage_purchases', 'manage_products', 'manage_customers', 'manage_suppliers',
    'manage_payments', 'manage_expenses', 'view_reports', 'manage_warehouse', 'manage_store', 'view_ledger', 'manage_ledger',
    'admin', 'manage_users', 'manage_backups', 'manage_payroll',
]

# --- Unified Enums (canonical values only) ---
SALE_PAYMENT_STATUSES = ('paid', 'partial', 'unpaid')
SALE_SOURCES = ('internal', 'online_store')
CHEQUE_STATUSES = ('pending', 'deposited', 'cleared', 'bounced', 'cancelled', 'under_collection')
PAYMENT_TYPES = (
    'sale_payment', 'supplier_payment', 'bill_payment', 'refund',
    'customer_payment', 'manual',
)
RECEIPT_SOURCE_TYPES = ('sale', 'manual', 'refund', 'adjustment', 'other')
PAYMENT_METHOD_CODES = ('cash', 'card', 'bank_transfer', 'cheque', 'e_wallet')
PAYMENT_METHOD_ALIASES = {
    'bank': 'bank_transfer',
}
DIRECTION_VALUES = ('incoming', 'outgoing')


def normalize_payment_method_code(method):
    """Normalize legacy payment method codes to canonical values."""
    if method is None:
        return method
    value = str(method).strip().lower()
    return PAYMENT_METHOD_ALIASES.get(value, value)

# Role hierarchy for user management (higher = more privileged)
ROLE_LEVELS = {
    'seller': 10,
    'accountant': 15,
    'branch_manager': 20,
    'manager': 25,
    'super_admin': 90,
    'developer': 95,
    'owner': 100,
}

PERMISSIONS = {
    'manage_sales': {'ar': 'إدارة المبيعات', 'en': 'Manage Sales'},
    'manage_purchases': {'ar': 'إدارة المشتريات', 'en': 'Manage Purchases'},
    'manage_products': {'ar': 'إدارة المنتجات', 'en': 'Manage Products'},
    'manage_customers': {'ar': 'إدارة العملاء', 'en': 'Manage Customers'},
    'manage_suppliers': {'ar': 'إدارة الموردين', 'en': 'Manage Suppliers'},
    'manage_payments': {'ar': 'إدارة المدفوعات', 'en': 'Manage Payments'},
    'manage_expenses': {'ar': 'إدارة المصروفات', 'en': 'Manage Expenses'},
    'view_reports': {'ar': 'عرض التقارير', 'en': 'View Reports'},
    'manage_warehouse': {'ar': 'إدارة المستودعات', 'en': 'Manage Warehouse'},
    'manage_store': {'ar': 'إدارة المتجر الإلكتروني', 'en': 'Manage Online Store'},
    'view_ledger': {'ar': 'عرض دفتر الأستاذ', 'en': 'View Ledger'},
    'manage_ledger': {'ar': 'إدارة دفتر الأستاذ', 'en': 'Manage Ledger'},
    'admin': {'ar': 'لوحة التحكم الإدارية', 'en': 'Admin Dashboard'},
    'manage_users': {'ar': 'إدارة المستخدمين', 'en': 'Manage Users'},
    'manage_backups': {'ar': 'إدارة النسخ الاحتياطي', 'en': 'Manage Backups'},
    'manage_payroll': {'ar': 'إدارة الرواتب', 'en': 'Manage Payroll'},
}

