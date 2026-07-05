"""
Browser verification of owner templates.
Navigates to each owner route and captures key text to verify rendering.
"""

import subprocess
import json
import time

BASE = "http://localhost:8001"

OWNER_ROUTES = [
    ("/owner/dashboard", ["لوحة التحكم الشاملة", "منطقة الإدارة العليا"]),
    ("/owner/users_list", ["المستخدمين", "قائمة"]),
    ("/owner/create_user", ["مستخدم", "جديد"]),
    ("/owner/company_info", ["بيانات", "الشركة"]),
    ("/owner/invoice_settings", ["فاتورة", "إعدادات"]),
    ("/owner/system_config", ["النظام", "إعدادات"]),
    ("/owner/database_tools", ["قاعدة", "بيانات"]),
    ("/owner/integrations", [" integrations", "WhatsApp"]),
    ("/owner/audit_logs", ["تدقيق", "سجل"]),
    ("/owner/error_audit_logs", ["أخطاء", "سجل"]),
    ("/owner/roles_permissions", ["أدوار", "صلاحيات"]),
    ("/owner/cards_vault", ["بطاقات", "خزينة"]),
    ("/owner/scheduled_backups", ["نسخ", "احتياطية"]),
    ("/owner/system_stats", ["إحصائيات", "النظام"]),
    ("/owner/reports", ["تقارير", "مالك"]),
    ("/owner/financial_overview", ["مالية", "نظرة"]),
    ("/owner/activity_monitor", ["مراقبة", "نشاط"]),
    ("/owner/backup_restore_instructions", ["استعادة", "نسخ"]),
]

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr

# Already logged in via browser session
results = []
for route, expected in OWNER_ROUTES:
    run(f'agent-browser open "{BASE}{route}"')
    time.sleep(1)
    text = run('agent-browser get text')
    ok = all(e in text for e in expected)
    results.append((route, ok, text[:200]))
    print(f"{'OK' if ok else 'FAIL'} | {route}")

print("\n" + "="*60)
for route, ok, snippet in results:
    print(f"{'[OK]' if ok else '[FAIL]'} {route}")
