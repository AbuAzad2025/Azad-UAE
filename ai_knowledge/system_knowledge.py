"""
System Knowledge - Complete Azad-UAE ERP reference.
Queryable by AI assistant to answer ANY question about the system.
"""
from datetime import datetime
from typing import Any

# ===== SYSTEM OVERVIEW =====
SYSTEM_INFO = {
    "name": "Azad-UAE ERP",
    "name_ar": "نظام أزاد لإدارة المؤسسات",
    "version": "2.0",
    "type": "Multi-tenant Cloud ERP",
    "stack": "Python 3.10, Flask, PostgreSQL, SQLAlchemy, Redis",
    "frontend": "Bootstrap 5, jQuery, Chart.js, DataTables",
    "ai": "Groq (llama-3.3-70b), scikit-learn MLP, TF-IDF semantic matching",
    "languages": "Arabic, English",
}

# ===== ROLE SYSTEM =====
ROLES: list[dict[str, Any]] = [
    {"slug": "owner", "level": 100, "name_en": "Owner", "name_ar": "مالك", "permissions": "all"},
    {"slug": "developer", "level": 95, "name_en": "Developer", "name_ar": "مطور", "permissions": "all"},
    {"slug": "super_admin", "level": 90, "name_en": "Super Admin", "name_ar": "مدير عام", "permissions": "all"},
    {"slug": "manager", "level": 25, "name_en": "Manager", "name_ar": "مدير",
     "permissions": ["manage_sales", "manage_purchases", "manage_products", "manage_customers",
                     "manage_suppliers", "manage_payments", "manage_expenses", "view_reports",
                     "manage_warehouse", "manage_store", "view_ledger", "manage_ledger", "manage_payroll"]},
    {"slug": "branch_manager", "level": 20, "name_en": "Branch Manager", "name_ar": "مدير فرع",
     "permissions": ["manage_sales", "manage_purchases", "manage_products", "manage_customers",
                     "manage_suppliers", "manage_payments", "manage_expenses", "view_reports",
                     "manage_warehouse", "manage_store", "view_ledger", "manage_ledger", "manage_payroll"]},
    {"slug": "accountant", "level": 15, "name_en": "Accountant", "name_ar": "محاسب",
     "permissions": ["manage_payments", "manage_expenses", "view_reports", "view_ledger",
                     "manage_ledger", "manage_payroll"]},
    {"slug": "seller", "level": 10, "name_en": "Seller", "name_ar": "بائع",
     "permissions": ["manage_sales", "manage_customers", "view_reports", "view_ledger"]},
]

# ===== PERMISSION CODES =====
PERMISSIONS: dict[str, dict[str, Any]] = {
    "manage_sales": {"name": "Manage Sales", "name_ar": "إدارة المبيعات", "category": "sales"},
    "manage_purchases": {"name": "Manage Purchases", "name_ar": "إدارة المشتريات", "category": "purchases"},
    "manage_products": {"name": "Manage Products", "name_ar": "إدارة المنتجات", "category": "products"},
    "manage_customers": {"name": "Manage Customers", "name_ar": "إدارة العملاء", "category": "customers"},
    "manage_suppliers": {"name": "Manage Suppliers", "name_ar": "إدارة الموردين", "category": "suppliers"},
    "manage_payments": {"name": "Manage Payments", "name_ar": "إدارة المدفوعات", "category": "finance"},
    "manage_expenses": {"name": "Manage Expenses", "name_ar": "إدارة المصروفات", "category": "finance"},
    "view_reports": {"name": "View Reports", "name_ar": "عرض التقارير", "category": "reports"},
    "manage_warehouse": {"name": "Manage Warehouse", "name_ar": "إدارة المستودعات", "category": "warehouse"},
    "manage_store": {"name": "Manage Store", "name_ar": "إدارة المتجر", "category": "store"},
    "view_ledger": {"name": "View Ledger", "name_ar": "عرض دفتر الأستاذ", "category": "finance"},
    "manage_ledger": {"name": "Manage Ledger", "name_ar": "إدارة دفتر الأستاذ", "category": "finance"},
    "admin": {"name": "Admin", "name_ar": "إدارة النظام", "category": "admin"},
    "manage_users": {"name": "Manage Users", "name_ar": "إدارة المستخدمين", "category": "admin"},
    "manage_backups": {"name": "Manage Backups", "name_ar": "إدارة النسخ الاحتياطي", "category": "admin"},
    "manage_payroll": {"name": "Manage Payroll", "name_ar": "إدارة الرواتب", "category": "admin"},
}

# ===== COMPLETE MODELS REFERENCE =====
MODELS: dict[str, dict[str, Any]] = {
    "Customer": {
        "table": "customers",
        "name_ar": "عميل",
        "fields": {
            "name": "String(150)",
            "phone": "String(50)",
            "email": "String(150)",
            "address": "Text",
            "credit_limit": "Numeric(12,2)",
            "balance": "Numeric(12,2)",
            "customer_type": "String(50) - regular/partner",
            "tax_number": "String(50)",
            "notes": "Text",
            "is_active": "Boolean",
        },
        "relationships": ["sales", "payments", "receipts", "product_partners"],
    },
    "Supplier": {
        "table": "suppliers",
        "name_ar": "مورد",
        "fields": {
            "name": "String(150)",
            "company_name": "String(150)",
            "phone": "String(50)",
            "email": "String(150)",
            "tax_number": "String(50)",
            "credit_limit": "Numeric(12,2)",
            "total_purchases_aed": "Numeric(12,2)",
            "rating": "Integer",
            "notes": "Text",
        },
        "relationships": ["purchases", "payments"],
    },
    "Product": {
        "table": "products",
        "name_ar": "منتج",
        "fields": {
            "name": "String(200)",
            "sku": "String(100)",
            "barcode": "String(100)",
            "cost_price": "Numeric(12,2)",
            "selling_price": "Numeric(12,2)",
            "current_stock": "Numeric(12,2)",
            "min_stock_level": "Numeric(12,2)",
            "category_id": "FK->product_categories.id",
            "unit": "String(50)",
            "location": "String(100)",
            "is_active": "Boolean",
        },
        "relationships": ["sale_lines", "purchase_lines", "stock_movements", "product_partners"],
    },
    "Sale": {
        "table": "sales",
        "name_ar": "فاتورة مبيعات",
        "fields": {
            "sale_number": "String(50)",
            "customer_id": "FK->customers.id",
            "sale_date": "DateTime",
            "subtotal": "Numeric(12,2)",
            "discount_amount": "Numeric(12,2)",
            "tax_amount": "Numeric(12,2)",
            "total_amount": "Numeric(12,2)",
            "paid_amount": "Numeric(12,2)",
            "balance_due": "Numeric(12,2)",
            "currency": "String(10)",
            "amount_aed": "Numeric(12,2)",
            "payment_status": "String(20) - paid/partial/unpaid",
            "status": "String(20) - active/cancelled/archived",
            "payment_method": "String(50)",
            "seller_id": "FK->users.id",
            "warehouse_id": "FK->warehouses.id",
        },
        "relationships": ["lines", "payments", "returns"],
    },
    "Purchase": {
        "table": "purchases",
        "name_ar": "فاتورة مشتريات",
        "fields": {
            "purchase_number": "String(50)",
            "supplier_id": "FK->suppliers.id",
            "purchase_date": "DateTime",
            "subtotal": "Numeric(12,2)",
            "total_amount": "Numeric(12,2)",
            "currency": "String(10)",
            "amount_aed": "Numeric(12,2)",
            "status": "String(20)",
            "warehouse_id": "FK->warehouses.id",
            "freight_cost": "Numeric(12,2)",
            "customs_duty": "Numeric(12,2)",
            "insurance_cost": "Numeric(12,2)",
        },
        "relationships": ["lines", "payments"],
    },
    "Payment": {
        "table": "payments",
        "name_ar": "دفعة",
        "fields": {
            "payment_number": "String(50)",
            "direction": "String(10) - incoming/outgoing",
            "customer_id": "FK->customers.id",
            "supplier_id": "FK->suppliers.id",
            "sale_id": "FK->sales.id",
            "purchase_id": "FK->purchases.id",
            "amount": "Numeric(12,2)",
            "currency": "String(10)",
            "amount_aed": "Numeric(12,2)",
            "payment_method": "String(50)",
            "payment_date": "DateTime",
            "reference": "String(100)",
            "notes": "Text",
            "cheque_id": "FK->cheques.id",
        },
    },
    "Expense": {
        "table": "expenses",
        "name_ar": "مصروف",
        "fields": {
            "expense_number": "String(50)",
            "category_id": "FK->expense_categories.id",
            "description": "Text",
            "amount": "Numeric(12,2)",
            "currency": "String(10)",
            "amount_aed": "Numeric(12,2)",
            "expense_date": "DateTime",
            "payment_method": "String(50)",
            "receipt_image": "String(255)",
            "branch_id": "FK->branches.id",
        },
    },
    "Cheque": {
        "table": "cheques",
        "name_ar": "شيك",
        "fields": {
            "cheque_number": "String(100)",
            "cheque_type": "String(20) - incoming/outgoing",
            "bank_name": "String(100)",
            "amount": "Numeric(12,2)",
            "currency": "String(10)",
            "amount_aed": "Numeric(12,2)",
            "issue_date": "Date",
            "due_date": "Date",
            "status": "String(20) - pending/deposited/cleared/bounced/cancelled",
            "drawer_name": "String(150)",
            "payee_name": "String(150)",
            "customer_id": "FK->customers.id",
            "supplier_id": "FK->suppliers.id",
        },
    },
    "GLJournalEntry": {
        "table": "gl_journal_entries",
        "name_ar": "قيد محاسبي",
        "fields": {
            "entry_number": "String(50)",
            "entry_date": "Date",
            "description": "Text",
            "is_posted": "Boolean",
            "reference_type": "String(50)",
            "reference_id": "Integer",
            "branch_id": "FK->branches.id",
        },
        "relationships": ["lines"],
    },
    "GLAccount": {
        "table": "gl_accounts",
        "name_ar": "حساب أستاذ",
        "fields": {
            "code": "String(20)",
            "name": "String(200)",
            "name_ar": "String(200)",
            "type": "String(20) - asset/liability/equity/revenue/expense",
            "parent_id": "FK->gl_accounts.id",
            "is_header": "Boolean",
            "liquidity_kind": "String(50)",
        },
    },
    "User": {
        "table": "users",
        "name_ar": "مستخدم",
        "fields": {
            "username": "String(80)",
            "email": "String(120)",
            "password_hash": "String(255)",
            "role_id": "FK->roles.id",
            "tenant_id": "FK->tenants.id",
            "branch_id": "FK->branches.id",
            "is_active": "Boolean",
            "is_owner": "Boolean",
            "full_name": "String(150)",
            "phone": "String(50)",
        },
    },
    "Tenant": {
        "table": "tenants",
        "name_ar": "منشأة",
        "fields": {
            "name": "String(150)",
            "slug": "String(100)",
            "business_type": "String(100)",
            "is_active": "Boolean",
            "enable_ai": "Boolean",
            "max_users": "Integer",
            "max_products": "Integer",
            "subscription_plan": "String(50)",
        },
        "note": "Root entity for multi-tenancy. Every record is scoped to a tenant.",
    },
    "Warehouse": {
        "table": "warehouses",
        "name_ar": "مستودع",
        "fields": {
            "name": "String(100)",
            "code": "String(50)",
            "warehouse_type": "String(20) - physical/online",
            "branch_id": "FK->branches.id",
            "is_active": "Boolean",
        },
    },
    "Partner": {
        "table": "partners",
        "name_ar": "شريك",
        "fields": {
            "name": "String(150)",
            "scope_type": "String(50)",
            "profit_share_percent": "Numeric(5,2)",
            "capital_amount": "Numeric(12,2)",
            "total_profit_share": "Numeric(12,2)",
            "total_withdrawn": "Numeric(12,2)",
        },
    },
    "Employee": {
        "table": "employees",
        "name_ar": "موظف",
        "fields": {
            "name": "String(150)",
            "phone": "String(50)",
            "position": "String(100)",
            "salary_base": "Numeric(12,2)",
            "branch_id": "FK->branches.id",
            "bank_account": "String(50)",
            "hiring_date": "Date",
        },
    },
    "AuditLog": {
        "table": "audit_logs",
        "name_ar": "سجل التدقيق",
        "fields": {
            "user_id": "FK->users.id",
            "action": "String(100)",
            "entity_type": "String(100)",
            "entity_id": "Integer",
            "details": "JSON",
            "ip_address": "String(50)",
            "created_at": "DateTime",
        },
    },
    "ErrorAuditLog": {
        "table": "error_audit_logs",
        "name_ar": "سجل الأخطاء",
        "fields": {
            "error_type": "String(100)",
            "error_message": "Text",
            "endpoint": "String(255)",
            "user_id": "FK->users.id",
            "request_data": "JSON",
            "traceback": "Text",
            "resolved": "Boolean",
            "resolution_notes": "Text",
        },
    },
}

# ===== ALL BLUEPRINTS / ROUTE GROUPS =====
ROUTES = {
    "AI Assistant": {
        "prefix": "/ai",
        "permission": "view_reports",
        "endpoints": ["/chat", "/assistant", "/predict-sales", "/analyze-margins",
                       "/business-insights", "/deep-analysis", "/cash-flow-prediction",
                       "/inventory-health", "/churn-prediction", "/optimize-inventory",
                       "/detect-patterns", "/recommend-price", "/check-stock",
                       "/analyze-customer/<id>", "/exchange-rate/<currency>",
                       "/system/summary", "/system/search/<term>",
                       "/system/add-customer", "/system/customer-balance/<name>",
                       "/knowledge/search", "/contextual-help/<page>"],
    },
    "Sales": {
        "prefix": "/sales",
        "permission": "manage_sales",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/cancel",
                       "/<id>/delete", "/<id>/print", "/<id>/archive", "/<id>/restore",
                       "/archived"],
    },
    "Purchases": {
        "prefix": "/purchases",
        "permission": "manage_purchases",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete", "/<id>/print"],
    },
    "Products": {
        "prefix": "/products",
        "permission": "manage_products",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete"],
    },
    "Customers": {
        "prefix": "/customers",
        "permission": "manage_customers",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete",
                       "/<id>/statement"],
    },
    "Suppliers": {
        "prefix": "/suppliers",
        "permission": "manage_suppliers",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete",
                       "/<id>/statement"],
    },
    "Payments": {
        "prefix": "/payments",
        "permission": "manage_payments",
        "endpoints": ["/", "/receipts", "/receipts/create", "/create_from_sale/<id>"],
    },
    "Expenses": {
        "prefix": "/expenses",
        "permission": "manage_expenses",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete"],
    },
    "Cheques": {
        "prefix": "/cheques",
        "permission": "manage_payments",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/<id>/delete",
                       "/<id>/clear", "/<id>/bounce"],
    },
    "Warehouse": {
        "prefix": "/warehouse",
        "permission": "manage_warehouse",
        "endpoints": ["/", "/create", "/<id>", "/<id>/edit", "/movements",
                       "/transfer", "/adjust"],
    },
    "Reports": {
        "prefix": "/reports",
        "permission": "view_reports",
        "endpoints": ["/", "/sales", "/purchases", "/customers",
                       "/profit-loss", "/cash-flow", "/treasury"],
    },
    "Ledger": {
        "prefix": "/ledger",
        "permission": "view_ledger",
        "endpoints": ["/", "/account/<id>", "/journal", "/trial-balance"],
    },
    "Payroll": {
        "prefix": "/payroll",
        "permission": "manage_payroll",
        "endpoints": ["/employees", "/salaries", "/advances"],
    },
    "POS": {
        "prefix": "/pos",
        "permission": "manage_sales",
        "endpoints": ["/", "/api/products", "/api/checkout", "/api/hold"],
    },
    "Owner": {
        "prefix": "/owner",
        "permission": "admin",
        "endpoints": ["/dashboard", "/users-list", "/config", "/company-info",
                       "/audit-logs", "/archived", "/sql-console",
                       "/database-tools", "/tenant-stores", "/tenant-ai",
                       "/invoice-settings", "/backups"],
    },
    "Users": {
        "prefix": "/users",
        "permission": "manage_users",
        "endpoints": ["/", "/create", "/<id>/edit", "/<id>/delete", "/<id>/profile"],
    },
    "Branches": {
        "prefix": "/branches",
        "permission": "manage_users",
        "endpoints": ["/", "/create", "/<id>/edit", "/<id>/delete"],
    },
    "Store": {
        "prefix": "/store",
        "permission": "manage_store",
        "endpoints": ["/admin", "/admin/settings", "/admin/products", "/admin/orders"],
    },
    "API": {
        "prefix": "/api",
        "permission": "manage_products",
        "endpoints": ["/products", "/customers", "/suppliers", "/sales", "/stock"],
    },
}

# ===== ACCOUNTING REFERENCE =====
ACCOUNTING = {
    "vat_uae": {
        "rate": "5%",
        "name": "VAT in UAE",
        "name_ar": "ضريبة القيمة المضافة في الإمارات",
        "details": "Standard rate 5%. Some sectors exempt (healthcare, education, transport).",
    },
    "vat_palestine": {
        "rate": "16%",
        "name": "VAT in Palestine",
        "name_ar": "ضريبة القيمة المضافة في فلسطين",
        "details": "Standard rate 16%. Applied to most goods and services.",
    },
    "vat_israel": {
        "rate": "17%",
        "name": "VAT in Israel",
        "name_ar": "ضريبة القيمة المضافة في إسرائيل",
        "details": "Standard rate 17%. Reduced rates for certain items.",
    },
    "account_types": [
        {"code": "asset", "name_ar": "أصل", "name_en": "Asset",
         "subtypes": ["current_asset", "fixed_asset", "other_asset"]},
        {"code": "liability", "name_ar": "خصم", "name_en": "Liability",
         "subtypes": ["current_liability", "long_term_liability"]},
        {"code": "equity", "name_ar": "حقوق ملكية", "name_en": "Equity",
         "subtypes": ["capital", "retained_earnings", "drawings"]},
        {"code": "revenue", "name_ar": "إيراد", "name_en": "Revenue",
         "subtypes": ["sales_revenue", "other_revenue"]},
        {"code": "expense", "name_ar": "مصروف", "name_en": "Expense",
         "subtypes": ["cost_of_goods_sold", "operating_expense", "other_expense"]},
    ],
    "financial_ratios": {
        "gross_margin": "Gross Profit / Revenue * 100",
        "net_margin": "Net Profit / Revenue * 100",
        "current_ratio": "Current Assets / Current Liabilities",
        "debt_to_equity": "Total Liabilities / Total Equity",
        "inventory_turnover": "COGS / Average Inventory",
        "roe": "Net Profit / Total Equity * 100",
    },
    "accounting_principles": {
        "double_entry": "Every transaction debits one account and credits another. Total debits = Total credits.",
        "accrual": "Revenue recognized when earned, expenses when incurred (not when cash moves).",
        "matching": "Expenses matched to revenues in the period they help generate.",
        "consistency": "Use same accounting methods across periods for comparability.",
    },
}

# ===== FEATURE REFERENCE =====
FEATURES: dict[str, dict[str, Any]] = {
    "Multi-tenancy": {
        "name_ar": "تعدد المنشآت",
        "description": "Each tenant has isolated data. Users belong to one tenant. Owner manages all tenants.",
        "permission": "admin",
    },
    "Branch Management": {
        "name_ar": "إدارة الفروع",
        "description": "Users can be scoped to branches. Reports can filter by branch.",
        "permission": "manage_users",
    },
    "AI Assistant": {
        "name_ar": "المساعد الذكي",
        "description": "Integrated AI chatbot. Supports Groq (llama-3.3-70b). Answers questions, performs actions, analyzes data.",
        "permission": "view_reports",
        "levels": {"basic": "Chat and light insights",
                    "advanced": "Basic + analytics, predictions, deep analysis",
                    "execute": "Advanced + create/update records via chat"},
    },
    "Point of Sale (POS)": {
        "name_ar": "نقطة البيع",
        "description": "Fast checkout interface. Product search, cart management, hold/unhold orders.",
        "permission": "manage_sales",
    },
    "Online Store": {
        "name_ar": "متجر إلكتروني",
        "description": "E-commerce storefront per tenant. Custom catalog, cart, checkout.",
        "permission": "manage_store",
    },
    "Payment Tracking": {
        "name_ar": "تتبع المدفوعات",
        "description": "Track incoming (customer payments) and outgoing (supplier payments). Multiple payment methods.",
        "permission": "manage_payments",
    },
    "Cheque Management": {
        "name_ar": "إدارة الشيكات",
        "description": "Track incoming/outgoing cheques. Status: pending, deposited, cleared, bounced, cancelled.",
        "permission": "manage_payments",
    },
    "Warehouse & Stock": {
        "name_ar": "المستودعات والمخزون",
        "description": "Multi-warehouse stock tracking. Movements, transfers, adjustments. Low stock alerts.",
        "permission": "manage_warehouse",
    },
    "General Ledger": {
        "name_ar": "دفتر الأستاذ العام",
        "description": "Double-entry accounting. Chart of accounts, journal entries, trial balance, financial reports.",
        "permission": "view_ledger",
    },
    "Multi-Currency": {
        "name_ar": "عملات متعددة",
        "description": "Transactions in any currency. Auto-conversion to AED. Exchange rate management.",
        "permission": "view_reports",
    },
    "Partner Profit Share": {
        "name_ar": "أرباح الشركاء",
        "description": "Track partner profit shares per transaction. Periodic profit distributions.",
        "permission": "manage_sales",
    },
    "Payroll": {
        "name_ar": "الرواتب",
        "description": "Employee management, salary processing, salary advances, payslips.",
        "permission": "manage_payroll",
    },
    "Audit Trail": {
        "name_ar": "سجل التدقيق",
        "description": "All mutations logged with user, timestamp, IP, entity. Owner accessible.",
        "permission": "admin",
    },
    "Error Audit": {
        "name_ar": "سجل الأخطاء",
        "description": "System errors captured with traceback, user context, request data. Resolvable.",
        "permission": "admin",
    },
}

# ===== COMMON USER QUESTIONS =====
FAQ = {
    "accountant": [
        {"q": "كيف أسجل قيد محاسبي؟", "a": "استخدم دفتر الأستاذ /ledger -> إضافة قيد. تأكد من تساوي المدين والدائن."},
        {"q": "كيف أشيد تقرير الأرباح والخسائر؟", "a": "اذهب إلى التقارير /reports/profit-loss"},
        {"q": "كيف أعمل كشف حساب لعميل؟", "a": "اذهب إلى العملاء -> العميل -> كشف حساب"},
        {"q": "ما هي أنواع الحسابات؟", "a": "أصل، خصم، حقوق ملكية، إيراد، مصروف"},
        {"q": "كيف أرجع فاتورة؟", "a": "اذهب إلى المبيعات -> الفاتورة -> إرجاع"},
    ],
    "manager": [
        {"q": "كيف أشوف تقرير المبيعات؟", "a": "التقارير /reports/sales - يعرض إجمالي المبيعات مع رسوم بيانية"},
        {"q": "كيف أحلل أداء البائعين؟", "a": "التقارير -> تحليل المبيعات -> تقارير الأداء"},
        {"q": "كيف أشوف المخزون المنخفض؟", "a": "المستودعات -> المخزون المنخفض /warehouse -> low_stock"},
        {"q": "كيف أضيف مستخدم جديد؟", "a": "الصلاحيات /users/create (يتطلب صلاحية manage_users)"},
    ],
    "seller": [
        {"q": "كيف أعمل فاتورة؟", "a": "المبيعات -> فاتورة جديدة /sales/create"},
        {"q": "كيف أبحث عن منتج؟", "a": "المنتجات -> بحث /products مع البحث بالاسم أو الرمز"},
        {"q": "كيف أستلم دفعة من عميل؟", "a": "المدفوعات -> استلام /payments/receipts/create"},
        {"q": "كيف أشوف رصيد العميل؟", "a": "العملاء -> العميل -> يظهر الرصيد في أعلى الصفحة"},
    ],
    "owner": [
        {"q": "كيف أضبط إعدادات النظام؟", "a": "لوحة المالك /owner/config"},
        {"q": "كيف أشوف سجل التدقيق؟", "a": "لوحة المالك -> سجل التدقيق /owner/audit-logs"},
        {"q": "كيف أعمل نسخة احتياطية؟", "a": "لوحة المالك -> النسخ الاحتياطي /owner/backups"},
        {"q": "كيف أضيف منشأة جديدة؟", "a": "سينتقل إلى /tenants - متاح للمالك فقط"},
        {"q": "كيف أضبط صلاحيات الذكاء الاصطناعي؟", "a": "لوحة المالك -> إعدادات AI /owner/tenant-ai"},
    ],
    "programmer": [
        {"q": "ما هي تقنيات النظام؟", "a": f"Python 3.10+, Flask, PostgreSQL, SQLAlchemy. Frontend: Bootstrap 5, jQuery."},
        {"q": "كيف أضيف مودل جديد؟", "a": "أنشئ ملف في models/، أضف class يرث db.Model، ثم run flask db migrate"},
        {"q": "كيف أضيف Route جديد؟", "a": "أنشئ ملف في routes/، عرّف Blueprint، ثم سجله في bootstrap/blueprints.py"},
        {"q": "ما هي صلاحيات API؟", "a": "API v1 في /api (JSON)، API v2 في /api/v2، GraphQL في /graphql"},
    ],
}


# ===== QUERY FUNCTIONS =====

def get_model_info(model_name: str) -> dict | None:
    """Get detailed info about a model by class name or table name."""
    model_name = model_name.replace(" ", "").replace("_", " ").strip()
    # Try direct match
    if model_name in MODELS:
        return MODELS[model_name]
    # Try case-insensitive
    for key, val in MODELS.items():
        if key.lower() == model_name.lower():
            return val
        if val["table"].lower() == model_name.lower():
            return {**val, "_key": key}
    # Try partial match
    for key, val in MODELS.items():
        if model_name.lower() in key.lower() or model_name.lower() in val["table"].lower():
            return {**val, "_key": key}
    return None


def get_permission_info(code: str) -> dict | None:
    """Get permission details by code."""
    return PERMISSIONS.get(code)


def get_role_info(slug: str) -> dict | None:
    """Get role details by slug."""
    for r in ROLES:
        if r["slug"] == slug:
            return r
    return None


def search_knowledge(query: str) -> list[dict]:
    """Search all knowledge bases for a query."""
    results = []
    q = query.lower()

    # Search models
    for name, info in MODELS.items():
        if q in name.lower() or q in info["table"].lower() or q in info["name_ar"]:
            results.append({"type": "model", "name": name, "info": info})

    # Search permissions
    for code, info in PERMISSIONS.items():
        if q in code.lower() or q in info["name_ar"]:
            results.append({"type": "permission", "code": code, "info": info})

    # Search roles
    for r in ROLES:
        if q in r["slug"] or q in r["name_ar"]:
            results.append({"type": "role", "info": r})

    # Search routes
    for name, info in ROUTES.items():
        if q in name.lower():
            results.append({"type": "route_group", "name": name, "info": info})

    # Search features
    for name, info in FEATURES.items():
        if q in name.lower() or q in info["name_ar"]:
            results.append({"type": "feature", "name": name, "info": info})

    # Search accounting
    for key, val in ACCOUNTING.items():
        if isinstance(val, dict) and q in str(val.get("name_ar", "")).lower():
            results.append({"type": "accounting", "key": key, "info": val})
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and q in str(item.get("name_ar", "")).lower():
                    results.append({"type": "accounting", "key": key, "info": item})

    return results


def get_contextual_help(page: str) -> dict | None:
    """Get help for a specific page/feature."""
    for name, info in ROUTES.items():
        if page.lower() in name.lower():
            return {"page": name, "endpoints": info["endpoints"],
                    "required_permission": info["permission"]}
    return None


def get_role_based_features(role_slug: str) -> list[dict]:
    """Get features accessible to a specific role."""
    role = get_role_info(role_slug)
    if not role:
        return []
    if role.get("permissions") == "all":
        return [{"name": k, "info": v} for k, v in FEATURES.items()]
    features = []
    for name, info in FEATURES.items():
        if info["permission"] in role.get("permissions", []):
            features.append({"name": name, "info": info})
    return features
