"""
Verify owner templates render correctly using HTTP requests.
Logs in as OWNER and checks each route for expected content.
"""

import requests
import re
import os

BASE = "http://localhost:8001"
LOGIN_URL = f"{BASE}/auth/login"
REPORT_PATH = os.path.join(os.path.dirname(__file__), 'owner_verify_report.txt')

session = requests.Session()
resp = session.get(LOGIN_URL)

# Extract CSRF token
csrf_match = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', resp.text)
csrf_token = csrf_match.group(1) if csrf_match else None

login_data = {
    "username": "OWNER",
    "password": "Azad@1983@2026@06@16",
    "login_type": "platform",
}
if csrf_token:
    login_data["csrf_token"] = csrf_token

resp = session.post(LOGIN_URL, data=login_data, allow_redirects=True)
logged_in = "auth/login" not in resp.url

OWNER_ROUTES = [
    ("/owner/dashboard", ["لوحة التحكم الشاملة"]),
    ("/owner/users-list", ["المستخدمين"]),
    ("/owner/users/create", ["مستخدم"]),
    ("/owner/company-info", ["بيانات"]),
    ("/owner/integrations", ["integrations"]),
    ("/owner/audit-logs", ["تدقيق"]),
    ("/owner/cards-vault", ["بطاقات"]),
    ("/owner/scheduled-backups", ["نسخ"]),
    ("/owner/system-stats", ["إحصائيات"]),
    ("/owner/reports", ["تقارير"]),
    ("/owner/financial-overview", ["مالية"]),
    ("/owner/activity-monitor", ["مراقبة"]),
    ("/owner/roles-permissions", ["أدوار"]),
    ("/owner/database-tools", ["قاعدة"]),
    ("/owner/config", ["إعدادات"]),
    ("/owner/invoice-settings", ["فاتورة"]),
    ("/owner/error-audit-logs", ["أخطاء"]),
    ("/owner/system-health", ["صحة"]),
    ("/owner/master-login-info", ["master"]),
    ("/owner/company-dashboard", ["شركات"]),
]

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write(f"Logged in: {logged_in}\n")
    f.write(f"Final URL after login: {resp.url}\n")
    f.write("="*70 + "\n")

    failures = []
    for route, expected in OWNER_ROUTES:
        try:
            resp = session.get(f"{BASE}{route}", timeout=30)
            status = resp.status_code
            text = resp.text
            ok = status == 200 and all(e in text for e in expected)
            if not ok:
                missing = [e for e in expected if e not in text]
                failures.append((route, status, missing))
            f.write(f"{'[OK]' if ok else '[FAIL]'} {route} (HTTP {status})\n")
        except Exception as e:
            failures.append((route, None, [str(e)]))
            f.write(f"[ERROR] {route}: {e}\n")

    f.write("="*70 + "\n")
    if failures:
        f.write(f"FAILURES: {len(failures)} routes\n")
        for route, status, missing in failures:
            f.write(f"  {route} | HTTP {status} | missing: {missing}\n")
    else:
        f.write("ALL ROUTES PASSED\n")
    f.write("="*70 + "\n")

print(f"Report written to: {REPORT_PATH}")
