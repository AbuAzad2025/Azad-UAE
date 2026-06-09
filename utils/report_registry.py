
REPORT_REGISTRY = [
    {
        'id': 'sales',
        'name_ar': 'تقرير المبيعات',
        'name_en': 'Sales Report',
        'endpoint': 'reports.sales',
        'icon': 'fa-shopping-cart',
        'color': 'success',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'reports.sales_export',
        'description': 'إحصائيات المبيعات والأرباح حسب الفترة والفرع',
    },
    {
        'id': 'purchases',
        'name_ar': 'تقرير المشتريات',
        'name_en': 'Purchases Report',
        'endpoint': 'reports.purchases',
        'icon': 'fa-truck-loading',
        'color': 'info',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'reports.purchases_export',
        'description': 'حركة المشتريات والموردين حسب الفترة',
    },
    {
        'id': 'inventory',
        'name_ar': 'تقرير المخزون',
        'name_en': 'Inventory Report',
        'endpoint': 'reports.inventory',
        'icon': 'fa-boxes',
        'color': 'warning',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'reports.inventory_export',
        'description': 'أرصدة المخزون الحالية وتقييمها',
    },
    {
        'id': 'receivables',
        'name_ar': 'الذمم المدينة',
        'name_en': 'Receivables',
        'endpoint': 'reports.receivables',
        'icon': 'fa-user-clock',
        'color': 'danger',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'reports.receivables_export',
        'description': 'تحليل أعمار الذمم المدينة حسب الفترة',
    },
    {
        'id': 'ar_reconciliation',
        'name_ar': 'مطابقة الذمم',
        'name_en': 'AR Reconciliation',
        'endpoint': 'reports.ar_reconciliation',
        'icon': 'fa-balance-scale-right',
        'color': 'secondary',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': False,
        'description': 'مطابقة حسابات الذمم (1130/3350/2115)',
    },
    {
        'id': 'inventory_reconciliation',
        'name_ar': 'تسوية المخزون',
        'name_en': 'Inventory Reconciliation',
        'endpoint': 'reports.inventory_reconciliation',
        'icon': 'fa-warehouse',
        'color': 'secondary',
        'category': 'مالية',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'reports.inventory_reconciliation_export',
        'description': 'تسوية المخزون مع القيود المحاسبية (1140)',
    },
    {
        'id': 'treasury',
        'name_ar': 'مركز الخزينة',
        'name_en': 'Treasury Center',
        'endpoint': 'treasury.treasury',
        'icon': 'fa-university',
        'color': 'success',
        'category': 'خزينة وضرائب',
        'permission': 'view_reports',
        'has_export': True,
        'export_endpoint': 'treasury.treasury_export',
        'description': 'المركز المالي والخزينة النقدية',
    },
    {
        'id': 'vat_return',
        'name_ar': 'إقرار ضريبة القيمة المضافة',
        'name_en': 'VAT Return',
        'endpoint': 'treasury.vat_return',
        'icon': 'fa-calculator',
        'color': 'info',
        'category': 'خزينة وضرائب',
        'permission': 'view_reports',
        'has_export': False,
        'description': 'إقرار ضريبة القيمة المضافة الدوري',
    },
    {
        'id': 'partners',
        'name_ar': 'تقرير الشركاء والتجار',
        'name_en': 'Partners Report',
        'endpoint': 'reports.partners',
        'icon': 'fa-handshake',
        'color': 'primary',
        'category': 'تقارير تشغيلية',
        'permission': 'view_reports',
        'has_export': False,
        'description': 'عمولات الشركاء والتجار وحصص الأرباح',
    },
    {
        'id': 'top_selling',
        'name_ar': 'الأكثر مبيعاً',
        'name_en': 'Top Selling',
        'endpoint': 'reports.top_selling',
        'icon': 'fa-trophy',
        'color': 'warning',
        'category': 'تقارير تشغيلية',
        'permission': 'view_reports',
        'has_export': False,
        'description': 'المنتجات الأكثر مبيعاً حسب الكمية والإيراد',
    },
    {
        'id': 'trial_balance',
        'name_ar': 'ميزان المراجعة',
        'name_en': 'Trial Balance',
        'endpoint': 'ledger.trial_balance',
        'icon': 'fa-balance-scale',
        'color': 'purple',
        'category': 'محاسبة',
        'permission': 'view_ledger',
        'has_export': False,
        'description': 'ميزان المراجعة العام للحسابات',
    },
    {
        'id': 'income_statement',
        'name_ar': 'قائمة الدخل',
        'name_en': 'Income Statement',
        'endpoint': 'ledger.income_statement',
        'icon': 'fa-chart-line',
        'color': 'purple',
        'category': 'محاسبة',
        'permission': 'view_ledger',
        'has_export': False,
        'description': 'قائمة الدخل والإيرادات والمصروفات',
    },
    {
        'id': 'balance_sheet',
        'name_ar': 'الميزانية العمومية',
        'name_en': 'Balance Sheet',
        'endpoint': 'ledger.balance_sheet',
        'icon': 'fa-file-invoice-dollar',
        'color': 'purple',
        'category': 'محاسبة',
        'permission': 'view_ledger',
        'has_export': False,
        'description': 'الميزانية العمومية والأصول والخصوم',
    },
]


REPORT_CATEGORIES = [
    {'id': 'مالية', 'name_ar': 'التقارير المالية', 'name_en': 'Financial Reports', 'icon': 'fa-chart-pie'},
    {'id': 'خزينة وضرائب', 'name_ar': 'الخزينة والضرائب', 'name_en': 'Treasury & Tax', 'icon': 'fa-university'},
    {'id': 'تقارير تشغيلية', 'name_ar': 'تقارير تشغيلية', 'name_en': 'Operational Reports', 'icon': 'fa-clipboard-list'},
    {'id': 'محاسبة', 'name_ar': 'التقارير المحاسبية', 'name_en': 'Accounting Reports', 'icon': 'fa-book'},
]


def get_visible_reports(user):
    allowed = []
    for r in REPORT_REGISTRY:
        perm = r.get('permission', 'view_reports')
        if hasattr(user, 'has_permission') and user.has_permission(perm):
            allowed.append(r)
    return allowed


def get_reports_by_category(user):
    grouped = {}
    for r in get_visible_reports(user):
        cat = r['category']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(r)
    return grouped
