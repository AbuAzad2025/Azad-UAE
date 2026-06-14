"""
i18n Analysis Script: Scan all target ERP templates for Arabic strings
and map them against existing TRANSLATIONS in utils/i18n.py.

Usage: python scripts/analyze_i18n.py
Output: scripts/i18n_analysis_report.txt
"""
import os
import re
import sys

# Force UTF-8 for stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = r'D:\Data\karaj\UAE\Azad-UAE'
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'scripts', 'i18n_analysis_report.txt')

OUTPUT = []
def log(text=""):
    print(text)
    OUTPUT.append(text)

TARGET_DIRS = [
    'templates/purchases', 'templates/customers', 'templates/suppliers',
    'templates/products', 'templates/payments', 'templates/cheques',
    'templates/reports', 'templates/warehouse', 'templates/receipts',
    'templates/returns', 'templates/invoices', 'templates/expenses',
    'templates/users', 'templates/branches', 'templates/printing',
    'templates/crm', 'templates/partners', 'templates/hr', 'templates/payroll',
]

def build_reverse_lookup():
    i18n_path = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')
    arabic_to_key = {}
    key_to_arabic = {}
    key_to_english = {}

    with open(i18n_path, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r"'([^']+)'\s*:\s*\{[^}]*'ar'\s*:\s*'([^']+)'[^}]*'en'\s*:\s*'([^']+)'"
    matches = re.findall(pattern, content)

    for eng_key, ar_text, en_text in matches:
        arabic_to_key[ar_text] = eng_key
        key_to_arabic[eng_key] = ar_text
        key_to_english[eng_key] = en_text

    log(f"[INFO] Loaded {len(arabic_to_key)} existing translations from utils/i18n.py")
    return arabic_to_key, key_to_arabic, key_to_english


def find_arabic_strings(filepath):
    findings = []
    arabic_char = re.compile(r'[\u0600-\u06FF]')

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        log(f"  [ERROR] Cannot read {filepath}: {e}")
        return findings

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not arabic_char.search(stripped):
            continue

        # --- ATTR: title, placeholder, aria-label, data-tooltip ---
        attr_patterns = [
            (r'title\s*=\s*"([^"]*[\u0600-\u06FF][^"]*)"', 'title'),
            (r'placeholder\s*=\s*"([^"]*[\u0600-\u06FF][^"]*)"', 'placeholder'),
            (r'aria-label\s*=\s*"([^"]*[\u0600-\u06FF][^"]*)"', 'aria-label'),
            (r'alt\s*=\s*"([^"]*[\u0600-\u06FF][^"]*)"', 'alt'),
        ]
        for attr_re, ctx in attr_patterns:
            for m in re.finditer(attr_re, stripped):
                val = m.group(1).strip()
                if val and '{{' not in val and '{%' not in val:
                    findings.append((filepath, line_num, ctx, val, stripped))

        # Skip lines with template variables for text extraction
        if '{{' in stripped or '{%' in stripped:
            continue

        # --- JS alert/confirm ---
        js_patterns = [
            (r"alert\s*\(\s*'([^']*[\u0600-\u06FF][^']*)'\s*\)", 'JS alert'),
            (r"confirm\s*\(\s*'([^']*[\u0600-\u06FF][^']*)'\s*\)", 'JS confirm'),
        ]
        for js_re, ctx in js_patterns:
            for m in re.finditer(js_re, stripped):
                val = m.group(1).strip()
                if val and '{{' not in val and '{%' not in val:
                    findings.append((filepath, line_num, ctx, val, stripped))

        # --- JS comments ---
        for m in re.finditer(r'//\s*([\u0600-\u06FF].*)$', stripped):
            val = m.group(1).strip()
            if val:
                findings.append((filepath, line_num, 'JS comment', val, stripped))

        # --- Text between tags ---
        for m in re.finditer(r'>([^<]*[\u0600-\u06FF][^<]*)<', stripped):
            val = m.group(1).strip()
            if not val or '{{' in val or '{%' in val or val.startswith('/') or '://' in val:
                continue
            ctx = 'text'
            if val.endswith(':'):
                ctx = 'label'
            elif '</option>' in stripped or '<option' in stripped:
                ctx = 'option'
            findings.append((filepath, line_num, ctx, val.rstrip(':'), stripped))

    return findings


def generate_english_key(arabic_text):
    common_keys = {
        'إدارة المشتريات والفواتير': 'Purchases & Invoices Management',
        'إدارة المشتريات': 'Purchase Management',
        'سجل المشتريات': 'Purchases Record',
        'إدارة العملاء': 'Customer Management',
        'إدارة الزبائن': 'Customer Management',
        'قاعدة بيانات شاملة لجميع العملاء': 'Comprehensive customer database',
        'قاعدة بيانات شاملة لجميع الموردين والشركات': 'Comprehensive supplier and companies database',
        'إدارة الموردين': 'Supplier Management',
        'إدارة المستودع والمخزون': 'Warehouse & Inventory Management',
        'إدارة المستودع': 'Warehouse Management',
        'المخزون والحركات وإدارة القطع': 'Inventory, Movements & Parts Management',
        'إدارة المنتجات والمخزون': 'Products & Inventory Management',
        'إدارة المستخدمين والصلاحيات': 'Users & Permissions Management',
        'إدارة المنتجات': 'Product Management',
        'إدارة المبيعات والتقارير': 'Sales & Reports Management',
        'سندات القبض والدفع': 'Receipt & Payment Vouchers',
        'سندات القبض': 'Receipt Vouchers',
        'سند قبض جديد': 'New Receipt Voucher',
        'سند دفع جديد': 'New Payment Voucher',
        'الزبون': 'Customer',
        'الزبائن': 'Customers',
        'الفواتير': 'Invoices',
        'إجمالي المنتجات': 'Total Products',
        'المنتجات المنخفضة': 'Low Stock Products',
        'المنتجات النافذة': 'Out of Stock Products',
        'معلومات المورد': 'Supplier Information',
        'بيانات فاتورة الشراء': 'Purchase Invoice Data',
        'فاتورة شراء جديدة': 'New Purchase Invoice',
        'العودة للمشتريات': 'Back to Purchases',
        'سجل المصروفات': 'Expenses Record',
        'سجل الشيكات': 'Cheques Record',
        'شيك جديد': 'New Cheque',
        'سجل مرتجعات فواتير البيع': 'Sales Returns Record',
        'الشيكات الواردة': 'Incoming Cheques',
        'الشيكات الصادرة': 'Outgoing Cheques',
        'الشيكات المؤرشفة': 'Archived Cheques',
        'تنبيهات الشيكات': 'Cheque Alerts',
        'إضافة مستخدم': 'Add User',
        'آخر دخول': 'Last Login',
        'حذف (المالك فقط)': 'Delete (Owner Only)',
        'فرع المستخدم': 'User Branch',
        'عام / بدون فرع': 'General / No Branch',
        'إدارة الشيكات': 'Cheque Management',
        'رقم السند': 'Voucher Number',
        'سجل الحركات': 'Movements Log',
        'المستودع الحالي': 'Current Warehouse',
        'اختر مستودع...': 'Select warehouse...',
        'كل المستودعات': 'All Warehouses',
        'الشركاء والمساهمين': 'Partners & Shareholders',
        'شريك جديد': 'New Partner',
        'الشريك': 'Partner',
        'رأس المال': 'Capital',
        'إعدادات الطباعة': 'Print Settings',
        'إعدادات الورق': 'Paper Settings',
        'حجم الورق': 'Paper Size',
        'اتجاه الطباعة': 'Print Orientation',
        'القالب النشط': 'Active Template',
        'لون الترويسة': 'Header Color',
        'اللون الثانوي': 'Accent Color',
        'خيارات الطباعة': 'Print Options',
        'إظهار الشعار': 'Show Logo',
        'رمز QR': 'QR Code',
        'علامة مائية': 'Watermark',
        'إظهار الشروط والأحكام': 'Show Terms & Conditions',
        'الحضور والانصراف': 'Attendance',
        'الحضور': 'Attendance',
        'الأقسام': 'Departments',
        'الإجازات': 'Leaves',
        'تسجيل دخول': 'Check In',
        'تسجيل خروج': 'Check Out',
        'قسم جديد': 'New Department',
        'توليد رواتب الفرع (دفعة واحدة)': 'Generate Branch Payroll (Batch)',
        'العملاء المتوقعون': 'Leads',
        'خط الأنابيب': 'Pipeline',
        'المرحلة': 'Stage',
        'الزبون (للبيع)': 'Customer',
        'المورد (للمشتريات)': 'Supplier',
        'إدارة الفرع': 'Branch Management',
        'الفروع': 'Branches',
        'فرع جديد': 'New Branch',
        'إدارة الفروع': 'Branches Management',
        'إضافة فرع': 'Add Branch',
        'تعديل الفرع': 'Edit Branch',
        'مشترى جديد': 'New Purchase',
        'فاتورة شراء': 'Purchase Invoice',
        'إدارة المخزون': 'Inventory Management',
        'المالية والمحاسبة': 'Finance & Accounting',
        'الرواتب وشؤون الموظفين': 'Payroll & HR',
        'قائمة الموظفين': 'Employees List',
        'إضافة موظف': 'Add Employee',
        'كشف الراتب': 'Salary Slip',
        'السلف والدفعات': 'Advances & Payments',
        'السلف والاقساط': 'Advances & Deductions',
        'الراتب الأساسي': 'Base Salary',
        'البدلات': 'Allowances',
        'الاستقطاعات': 'Deductions',
        'صافي الراتب': 'Net Salary',
        'تأكيد الصرف': 'Confirm Payroll',
        'إجمالي الرواتب': 'Total Payroll',
        'عدد الموظفين': 'Employee Count',
        'الموظفين': 'Employees',
        'مصروف جديد': 'New Expense',
        'التصنيف': 'Category',
        'المستوى': 'Level',
        'النوع': 'Type',
        'النسبة': 'Percentage',
        'الطريقة': 'Method',
        'إضافة مستودع': 'Add Warehouse',
        'المستودع الرئيسي': 'Main Warehouse',
        'إزالة الفلتر': 'Remove Filter',
        'الكل --': '-- All --',
        'فاتورة بيع جديدة': 'New Sales Invoice',
        'سند قبض': 'Receipt Voucher',
        'سند دفع': 'Payment Voucher',
        'معتمد': 'Approved',
        'قيد المراجعة': 'Pending Review',
        'مرفوض': 'Rejected',
        'الزبون والفرع': 'Customer & Branch',
        'إدارة المخزون وحركاته': 'Inventory & Movements Management',
        'حركات المخزون وسجل الجرد': 'Stock Movements & Audit Log',
        'تقارير المبيعات والمشتريات': 'Sales & Purchases Reports',
        'كل الزبائن': 'All Customers',
        'تجار': 'Merchants',
        'عادي': 'Regular',
        'متأخر': 'Overdue',
        'معطل': 'Disabled',
        'كلاسيكي': 'Classic',
        'حديث': 'Modern',
        'بسيط': 'Simple',
        'أقلية': 'Minimal',
        'خليجي': 'Gulf',
        'عمودي': 'Portrait',
        'أفقي': 'Landscape',
    }
    return common_keys.get(arabic_text)


def scan_all_files():
    all_files = []
    for target in TARGET_DIRS:
        dir_path = os.path.join(PROJECT_ROOT, target)
        if os.path.isdir(dir_path):
            for root, dirs, files in os.walk(dir_path):
                dirs[:] = [d for d in dirs if not d.startswith('__')]
                for f in files:
                    if f.endswith('.html'):
                        all_files.append(os.path.join(root, f))
    return sorted(all_files)


# ===== MAIN =====
arabic_to_key, key_to_arabic, key_to_english = build_reverse_lookup()
all_files = scan_all_files()
log(f"\n[INFO] Found {len(all_files)} template files in target directories\n")

# Analyze each file
file_findings = {}
existing_key_matches = {}
new_strings = set()

for filepath in all_files:
    relpath = os.path.relpath(filepath, PROJECT_ROOT)
    findings = find_arabic_strings(filepath)
    if findings:
        file_findings[relpath] = findings
        for (_, _, _, ar, _) in findings:
            if ar in arabic_to_key:
                existing_key_matches[ar] = arabic_to_key[ar]
            else:
                new_strings.add(ar)

total_arabic = sum(len(v) for v in file_findings.values())

# Generate new key suggestions
new_key_suggestions = {}
unmapped = []
for ar in sorted(new_strings):
    suggested = generate_english_key(ar)
    if suggested:
        new_key_suggestions[ar] = suggested
    else:
        unmapped.append(ar)

# ===== REPORT =====
sep = "=" * 78
log(sep)
log("i18n ANALYSIS REPORT — Arabic to t() conversion")
log(f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
log(sep)

log(f"\n{sep}")
log("1. FILES THAT NEED PROCESSING (sorted by Arabic string count)")
log(f"{sep}\n")

sorted_files = sorted(file_findings.items(), key=lambda x: len(x[1]), reverse=True)
for relpath, findings in sorted_files:
    log(f"  {relpath:<70s} {len(findings):>3d}")
log(f"\n  TOTAL: {len(file_findings)} files with {total_arabic} Arabic strings")

log(f"\n{sep}")
log("2. ARABIC STRINGS MATCHING EXISTING TRANSLATIONS (reusable keys)")
log(f"{sep}\n")

if existing_key_matches:
    for ar_text in sorted(existing_key_matches.keys(), key=lambda x: -len(x)):
        eng_key = existing_key_matches[ar_text]
        log(f"  {ar_text:<55s} -> t('{eng_key}')")
    log(f"\n  COUNT: {len(existing_key_matches)} matches")
else:
    log("  (none)")

log(f"\n{sep}")
log("3. NEW KEYS NEEDED (no existing translation) — with suggested English keys")
log(f"{sep}\n")

if new_key_suggestions:
    for ar_text, eng_key in sorted(new_key_suggestions.items(), key=lambda x: -len(x[0])):
        log(f"  {ar_text:<55s} -> t('{eng_key}')")
    log(f"\n  COUNT: {len(new_key_suggestions)} new keys")
else:
    log("  (none)")

if unmapped:
    log(f"\n  ** UNMAPPED (no suggestion available):")
    for ar_text in sorted(unmapped, key=lambda x: -len(x)):
        log(f"    {ar_text}")
    log(f"\n  COUNT: {len(unmapped)} unmapped")

log(f"\n{sep}")
log("4. DETAILED FILE-BY-FILE BREAKDOWN")
log(f"{sep}\n")

for relpath, findings in sorted_files:
    log(f"\n--- {relpath} ({len(findings)} strings) ---")
    for (fpath, line_num, ctx, ar, full_line) in findings:
        if ar in arabic_to_key:
            status = f"EXISTS: t('{arabic_to_key[ar]}')"
        elif ar in new_key_suggestions:
            status = f"NEW: t('{new_key_suggestions[ar]}')"
        else:
            status = "UNMAPPED"
        log(f"  L{line_num:<5} [{ctx:<12}] {ar:<50s} -> {status}")

log(f"\n{sep}")
log("SUMMARY")
log(f"{sep}")
log(f"  Files to process:         {len(file_findings)}")
log(f"  Total Arabic strings:     {total_arabic}")
log(f"  Reusable (existing keys): {len(existing_key_matches)}")
log(f"  New keys needed:          {len(new_key_suggestions)}")
log(f"  Unmapped:                 {len(unmapped)}")
log(f"{sep}")

# Write to file
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUTPUT))

log(f"\n[DONE] Full report written to: {OUTPUT_FILE}")
