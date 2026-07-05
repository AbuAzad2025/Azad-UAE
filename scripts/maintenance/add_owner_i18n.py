"""
Add missing i18n keys for common hardcoded Arabic strings in owner templates.
Only processes strings appearing in >= 2 templates (shared UI labels).
"""

import os
import re
import ast

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
PROJECT_ROOT = os.path.abspath(PROJECT_ROOT)
OWNER_DIR = os.path.join(PROJECT_ROOT, 'templates', 'owner')
I18N_PATH = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')

# Manual mapping: Arabic -> English key (for common terms)
KNOWN_KEYS = {
    'نظام المحاسبة': 'Accounting_System',
    'غير محدد': 'Not_Specified',
    'فقط': 'Only',
    'تاريخ الإنشاء': 'Created_Date',
    'تاريخ الانتهاء': 'Expiry_Date',
    'آخر استخدام': 'Last_Used',
    'آخر تحديث': 'Last_Updated',
    'إعدادات الفواتير': 'Invoice_Settings',
    'العملة الافتراضية': 'Default_Currency',
    'إعدادات النظام المتقدمة': 'Advanced_System_Settings',
    'احصل على': 'Get',
    'الأكثر شيوعاً': 'Most_Common',
    'المتغيرات المتاحة:': 'Available_Variables',
    'عدد الاستخدام': 'Usage_Count',
    'عدد السجلات': 'Record_Count',
    'كل ساعة': 'Every_Hour',
    'لوحة المالك': 'Owner_Dashboard',
    'مالك النظام': 'System_Owner',
    'نوع البطاقة': 'Card_Type',
    'إجراء': 'Action',
    'الإجراءات': 'Actions',
    'الحالة': 'Status',
    'نشط': 'Active',
    'معطل': 'Inactive',
    'معلق': 'Pending',
    'مفتوحة': 'Open',
    'مقفلة': 'Closed',
    'التبرعات': 'Donations',
    'المدفوعات': 'Payments_2',
    'المستخدمين': 'Users_2',
    'العملاء': 'Customers_3',
    'المنتجات': 'Products_2',
    'المبيعات': 'Sales_3',
    'الفواتير': 'Invoices',
    'الشيكات': 'Cheques_2',
    'المصاريف': 'Expenses_2',
    'الرواتب': 'Salaries_2',
    'الشركة الحالية': 'Current_Company',
    'جميع الشركات': 'All_Companies',
    'إيرادات السنة': 'Year_Revenue',
    'إيرادات المنصة': 'Platform_Revenue',
    'إجمالي المستحقات': 'Total_Receivables',
    'إجمالي مستحقات المنصة': 'Platform_Receivables',
    'فواتير متأخرة': 'Overdue_Invoices',
    'فواتير متأخرة المنصة': 'Platform_Overdue_Invoices',
    'قيمة المخزون': 'Inventory_Value',
    'قيمة مخزون المنصة': 'Platform_Inventory_Value',
    'أداء الفروع': 'Branch_Performance',
    'الفرع': 'Branch_3',
    'إجمالي المبيعات': 'Total_Sales_Amount',
    'مبيعات الشهر': 'Month_Sales',
    'إجمالي المصاريف': 'Total_Expenses',
    'مؤشر الربح': 'Profit_Index',
    'لا توجد بيانات للفروع': 'No_Branch_Data',
    'أداء فروع المنصة': 'Platform_Branch_Performance',
    'جميع الشركات': 'All_Companies_2',
    'قاعدة البيانات': 'Database',
    'إدارة الجداول': 'Table_Management',
    'إعدادات قاعدة البيانات': 'Database_Settings',
    'إحصائيات قاعدة البيانات': 'Database_Stats',
    'السجلات المؤرشفة': 'Archived_Records',
    'النسخ الاحتياطية': 'Backups_3',
    'الخزينة السرية': 'Secret_Vault',
    'التقارير': 'Reports_2',
    'النسخ المجدول': 'Scheduled_Backups',
    'مسح الذاكرة': 'Clear_Cache',
    'البطاقات المشفرة': 'Encrypted_Cards',
    'حفظ آمن لبطاقات الائتمان بتشفير عالي الأمان': 'Secure_Card_Storage',
    'خزينة البطاقات': 'Card_Vault',
    'تشفير AES-256': 'AES256_Encryption',
    'إعدادات التينانت': 'Tenant_Settings',
    'اسم النشاط، الشعار، العنوان، التواصل': 'Tenant_Info_Description',
    'تظهر في الفواتير وصفحة الدخول': 'Shows_In_Invoices_Login',
    'بيانات التينانت': 'Tenant_Data',
    'ترويسات الفواتير': 'Invoice_Headers',
    'إعدادات النظام': 'System_Settings_2',
    'طرق دفع المتاجر': 'Store_Payment_Methods',
    'إدارة التينانتس': 'Tenants_Management',
    'متاجر التينانتس': 'Tenant_Stores',
    'AI للتينانتس': 'Tenant_AI',
    'الاتصالات': 'Connections',
    'المستخدمون والفروع': 'Users_And_Branches',
    'إدارة المستخدمين وصلاحياتهم وفروع النشاط': 'Users_Permissions_Branches',
    'قائمة المستخدمين': 'Users_List',
    'إضافة مستخدم': 'Add_User',
    'إدارة الفروع': 'Branch_Management',
    'الأدوار والصلاحيات': 'Roles_And_Permissions',
    'سجل التدقيق': 'Audit_Log',
    'سجل أخطاء النظام': 'System_Error_Log',
    'مراقبة النظام': 'System_Monitoring',
    'صحة النظام': 'System_Health_2',
    'المراقبة الحية': 'Live_Monitoring',
    'سجل الأخطاء': 'Error_Log',
    'سجل الدخول': 'Login_History_2',
    'الأداء': 'Performance_2',
    'تنبيهات أمنية': 'Security_Alerts_2',
    'كلمة المرور الرئيسية': 'Master_Password',
    'تحليلات متقدمة': 'Advanced_Analytics',
    'رؤى عميقة وتنبؤات مالية': 'Deep_Insights_Financial_Forecasts',
    'لوحة مالية': 'Financial_Dashboard',
    'تحليل المبيعات': 'Sales_Analysis',
    'تحليل العملاء': 'Customer_Analysis',
    'توقعات مالية': 'Financial_Forecasts',
    'أداء المنتجات': 'Product_Performance',
    'إعدادات الفواتير': 'Invoice_Settings_2',
    'إعدادات العملة': 'Currency_Settings',
    'إعدادات البريد': 'Email_Settings_2',
    'إعدادات SMS': 'SMS_Settings',
    'إعدادات WhatsApp': 'WhatsApp_Settings',
    'بوابات الدفع': 'Payment_Gateways',
    'إعدادات الضرائب': 'Tax_Settings',
    'إعدادات الأمان': 'Security_Settings',
    'القائمة البيضاء IP': 'IP_Whitelist',
    'سجل الأخطاء': 'Error_Log_2',
    'سجل الأمان': 'Security_Log',
    'سجل الدخول': 'Login_Log',
    'العمليات': 'Operations',
    'الأخطاء': 'Errors',
    'التحذيرات': 'Warnings',
    'المعلومات': 'Information',
    'الأداء': 'Performance_3',
    'ساعة': 'Hour',
    'دقيقة': 'Minute',
    'يوم': 'Day',
    'أسبوع': 'Week',
    'شهر': 'Month',
    'سنة': 'Year',
    'إجمالي المبالغ المدفوعة': 'Total_Paid_Amount',
    'إجمالي المبالغ المستحقة': 'Total_Due_Amount',
    'المبلغ المدفوع': 'Paid_Amount',
    'المبلغ المستحق': 'Due_Amount',
    'منطقة الإدارة العليا': 'High_Admin_Area',
    'جميع العمليات في هذه اللوحة مسجلة لأغراض التدقيق والأمان': 'All_Operations_Audited',
    'عرض الكل': 'View_All',
    'التقارير': 'Reports_3',
    'المستخدمين': 'Users_3',
    'العملاء': 'Customers_4',
    'المبيعات': 'Sales_4',
    'إيرادات المنصة': 'Platform_Revenue_2',
    'إيرادات السنة': 'Year_Revenue_2',
    'فاتورة': 'Invoice_2',
    'ميزان المراجعة': 'Trial_Balance_2',
    'لا توجد بيانات': 'No_Data',
    'الشركة': 'Company_3',
    'الحالة': 'Status_2',
    'إجراء': 'Action_2',
}

def extract_translations(path):
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    match = re.search(r'TRANSLATIONS\s*=\s*\{', source)
    if not match:
        return {}, source, 0, 0
    start = match.end() - 1
    brace_count = 0
    end = start
    for i, ch in enumerate(source[start:], start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    try:
        translations = ast.literal_eval(source[start:end])
    except Exception:
        return {}, source, 0, 0
    return translations, source, start, end

def find_hardcoded(content):
    results = []
    for m in re.finditer(r'[\u0600-\u06FF][\u0600-\u06FF\s\d\(\)\[\]\{\}/\\.,:;!?\'%]*', content):
        start, end = m.span()
        text = m.group().strip()
        if len(text) < 2:
            continue
        prefix = content[max(0, start-30):start]
        suffix = content[end:min(len(content), end+10)]
        if re.search(r'\{\{\s*$', prefix) or re.search(r'^\s*\}\}', suffix):
            continue
        if re.search(r'\{%\s*$', prefix) or re.search(r'^\s*%\}', suffix):
            continue
        if re.search(r'\w+\s*=\s*["\'][^"\']*$', prefix):
            continue
        if re.search(r'["/\\]', prefix[-5:]):
            continue
        before = content[:start]
        if '<script' in before and '</script>' not in before.split('<script')[-1]:
            continue
        if '<style' in before and '</style>' not in before.split('<style')[-1]:
            continue
        last_lt = before.rfind('<')
        last_gt = before.rfind('>')
        if last_lt > last_gt:
            continue
        if re.search(r"t\(\s*['\"]", prefix[-15:]):
            continue
        results.append(text)
    return results

def add_to_i18n(new_entries):
    """Append new entries to TRANSLATIONS dict in i18n.py."""
    translations, source, dict_start, dict_end = extract_translations(I18N_PATH)

    # Filter out entries that already exist
    existing_keys = set(translations.keys())
    truly_new = {k: v for k, v in new_entries.items() if k not in existing_keys}

    if not truly_new:
        print("All keys already exist in TRANSLATIONS.")
        return True, 0

    # Find the closing brace of TRANSLATIONS
    match = re.search(r'TRANSLATIONS\s*=\s*\{', source)
    if not match:
        print("ERROR: Could not find TRANSLATIONS dict")
        return False, 0

    start = match.end() - 1
    brace_count = 0
    end = start
    for i, ch in enumerate(source[start:], start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i
                break

    # Build new entries text
    new_lines = []
    for key, ar_text in sorted(truly_new.items()):
        # Escape single quotes in Arabic text
        safe_ar = ar_text.replace("'", "\\'")
        new_lines.append(f"    '{key}': {{'ar': '{safe_ar}', 'en': '{key}'}},")

    insert_text = '\n' + '\n'.join(new_lines)

    new_source = source[:end] + insert_text + '\n' + source[end:]

    with open(I18N_PATH, 'w', encoding='utf-8') as f:
        f.write(new_source)
    return True, len(truly_new)

def replace_in_templates(ar_to_key):
    modified = 0
    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content
        # Replace known strings (longest first to avoid partial matches)
        for ar_text, key in sorted(ar_to_key.items(), key=lambda x: -len(x[0])):
            # Only replace if it's standalone text (between > and <)
            pattern = re.compile(r'>(\s*' + re.escape(ar_text) + r'\s*)<')
            content = pattern.sub(f">{{{{ t('{key}') }}}}<", content)

        if content != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            modified += 1
    return modified

def main():
    print("=" * 70)
    print("ADD OWNER I18N KEYS")
    print("=" * 70)

    # 1. Collect hardcoded strings and their frequencies
    all_strings = {}
    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        texts = find_hardcoded(content)
        for text in texts:
            all_strings.setdefault(text, 0)
            all_strings[text] += 1

    # 2. Filter to strings we know how to translate (in KNOWN_KEYS)
    new_entries = {}
    matched_count = 0
    for ar_text, count in all_strings.items():
        if ar_text in KNOWN_KEYS:
            key = KNOWN_KEYS[ar_text]
            new_entries[key] = ar_text
            matched_count += 1

    print(f"Found {len(all_strings)} unique hardcoded strings")
    print(f"Matched {matched_count} with KNOWN_KEYS")
    print(f"New entries to add: {len(new_entries)}")

    if not new_entries:
        print("Nothing to add.")
        return

    # 3. Add to i18n.py
    success, added_count = add_to_i18n(new_entries)
    if success:
        print(f"Added {added_count} new keys to utils/i18n.py")
    else:
        print("ERROR adding to i18n.py")
        return

    # 4. Replace in templates
    ar_to_key = {v: k for k, v in new_entries.items()}
    modified = replace_in_templates(ar_to_key)
    print(f"Modified {modified} template files")

    print("=" * 70)

if __name__ == '__main__':
    main()
