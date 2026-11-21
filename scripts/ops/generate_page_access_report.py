#!/usr/bin/env python3
"""Generate docs/PAGE_ACCESS_MATRIX.md from the live route map and login tests.

Every GET HTML page is visited as each seeded user type. The report records the
page name, its function (from the template title/heading), which roles can open
it and which are refused, plus decorators and notes.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_CACHE_PATH = str(Path(tempfile.gettempdir()) / "azad_page_access_sweep_cache.json")

# Never bake credentials into the script: the access report is a diagnostic
# run against an explicitly configured local database.
os.environ.setdefault("DATABASE_URL", os.environ.get("AUDIT_DATABASE_URL", ""))
os.environ.setdefault("SECRET_KEY", os.environ.get("AUDIT_SECRET_KEY", ""))
os.environ.setdefault("OWNER_PASSWORD", os.environ.get("AUDIT_OWNER_PASSWORD", ""))
if not os.environ.get("DATABASE_URL") or not os.environ.get("OWNER_PASSWORD"):
    raise SystemExit("Set AUDIT_DATABASE_URL and AUDIT_OWNER_PASSWORD before running the access report.")

from app.factory import create_app  # noqa: E402

app = create_app()
# The app's 403/404/500 handlers re-raise when DEBUG is on; turn it off so the
# test client receives the real HTTP status a browser would see.
app.config["DEBUG"] = False
app.config["PROPAGATE_EXCEPTIONS"] = False
app.config["WTF_CSRF_ENABLED"] = False

_TENANT_PASSWORD = os.environ.get("AUDIT_TENANT_PASSWORD", "")
USERS = [
    ("owner", os.environ.get("AUDIT_OWNER_USERNAME", "owner"), os.environ["OWNER_PASSWORD"], "مالك المنصة"),
    ("manager", "iso01_manager", _TENANT_PASSWORD, "مدير الشركة"),
    ("accountant", "iso01_accountant", _TENANT_PASSWORD, "المحاسب"),
    ("seller", "iso01_seller", _TENANT_PASSWORD, "البائع"),
    ("cashier", "iso01_cashier", _TENANT_PASSWORD, "الكاشير"),
    ("inventory", "iso01_inventory", _TENANT_PASSWORD, "أمين المخزون"),
]

PAGE_NAME_OVERRIDES = {
    "/": "الصفحة الرئيسية",
    "/dashboard": "لوحة التحكم",
    "/app": "لوحة التحكم",
    "/welcome": "لوحة التحكم",
    "/my-profile": "الملف الشخصي",
}

MODULE_DESCRIPTIONS = {
    "main": "لوحة التحكم والصفحة الرئيسية",
    "pos": "نقطة البيع، الجلسات، شاشة المطبخ وعرض العميل",
    "sales": "إدارة المبيعات والفواتير",
    "purchases": "إدارة المشتريات ومرتجعاتها",
    "products": "كتالوج المنتجات والفئات والاستيراد",
    "customers": "إدارة الزبائن وكشوف الحسابات",
    "suppliers": "إدارة الموردين",
    "payments": "المدفوعات والسندات والإيصالات",
    "cheques": "إدارة الشيكات الواردة والصادرة",
    "receipts": "إدارة الإيصالات",
    "ledger": "دفتر الأستاذ العام والقيود والتقارير المحاسبية",
    "admin_ledger": "إدارة الحسابات والقيود على مستوى المنصة",
    "advanced_ledger": "التحليلات المحاسبية المتقدمة والإعدادات",
    "reports": "التقارير المالية والتشغيلية",
    "hr": "الموارد البشرية: الحضور والإجازات",
    "payroll": "الرواتب والسلف والموظفون",
    "assets": "الأصول الثابتة والإهلاك",
    "warehouse": "المستودعات والمخزون والحركات",
    "transfers": "التحويلات بين المستودعات",
    "unified_inventory": "جرد الموحد: الحملات والشحنات والضمان",
    "maintenance": "الصيانة: أوامر العمل والقطع والتقارير",
    "branches": "الفروع",
    "budget": "الموازنات",
    "crm": "إدارة علاقات العملاء",
    "quotations": "عروض الأسعار",
    "returns": "مرتجعات المبيعات",
    "shipments": "الإرساليات",
    "partners": "الشركاء والتوزيعات",
    "projects": "المشاريع",
    "tickets": "تذاكر الدعم",
    "store": "المتجر الإلكتروني وإدارته",
    "shop": "واجهة المتجر للعميل",
    "email_marketing": "التسويق عبر البريد",
    "marketing": "الحملات التسويقية",
    "gamification": "لوحة المتصدرين والإحصائيات",
    "tenant_backups": "النسخ الاحتياطي للتينانت",
    "monitoring": "مراقبة النظام",
    "users": "إدارة المستخدمين",
    "my_profile": "الملف الشخصي",
    "auth": "تسجيل الدخول والمصادقة",
    "public": "الصفحات العامة (الرئيسية، تواصل، تسعير)",
    "owner": "لوحة التحكم الخاصة بمالك المنصة",
    "owner_admin": "إدارة المنصة",
    "payment_vault": "خزنة الدفع والباقات",
    "super_admin": "لوحة المسؤول الأعلى",
    "graphql": "واجهة GraphQL",
}

SKIP_MODULES = {"api", "ai", "graphql", "static", "api_analytics", "api_enhanced"}
SKIP_WORDS = ("api", "export", "download", "qr", "stream", "invoice.xml", "status", "well-known")
# Visiting these during a sweep would log the user out or mutate state.
SIDE_EFFECT_URLS = {
    "/auth/logout",
    "/payment-vault/lock",
    "/payment-vault/unlock",
    "/owner/convert-database",
    "/owner/data-cleanup",
    "/owner/sql-console",
    "/owner/verify-backups",
    "/whatsapp/test",
    "/pos/grid",
}


def route_rows():
    rows = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        ep, url = rule.endpoint, str(rule)
        if not ({"GET"} & rule.methods):
            continue
        if ep.split(".")[0] in SKIP_MODULES:
            continue
        if any(w in ep.lower() or w in url.lower() for w in SKIP_WORDS):
            continue
        if "<" in url:
            continue
        rows.append((ep, url))
    return rows


def page_meta(ep: str) -> dict:
    func = app.view_functions.get(ep)
    meta = {"module": ep.split(".")[0], "view": ep.split(".")[-1], "decorators": [], "template": ""}
    if func is None:
        return meta
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        source = ""
    for dec in re.findall(r"@([\w.]+)(?:\(([^)]*)\))?", source):
        if dec[0] in {
            "login_required",
            "permission_required",
            "owner_required",
            "owner_only",
            "company_admin_required",
            "csrf_protect",
            "rate_limit",
            "limit",
            "feature_guard",
        }:
            meta["decorators"].append((dec[0] + ("(" + dec[1][:60] + ")" if dec[1] else "")).strip())
    m = re.search(r'render_template\(\s*["\']([^"\']+)', source)
    if m:
        meta["template"] = m.group(1)
    return meta


def arabic_title(template: str) -> str:
    if not template:
        return ""
    path = ROOT / "templates" / template
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\{%\s*block title\s*%\}(.*?)\{%\s*endblock", text, re.S)
    if m:
        clean = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", m.group(1), flags=re.S)
        clean = re.sub(r"\s+", " ", clean).strip(" -\u2013")
        if clean and len(clean) <= 70 and re.search(r"[\u0600-\u06FF]", clean):
            return clean[:80]
    m = re.search(r"<h[123][^>]*>(.*?)</h[123]>", text, re.S)
    if m:
        clean = re.sub(r"<[^>]+>|\{\{.*?\}\}|\{%.*?%\}", "", m.group(1), flags=re.S)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            return clean[:80]
    return ""


def template_features(template: str) -> str:
    """List the UI capabilities visible in the template source."""
    if not template:
        return "—"
    path = ROOT / "templates" / template
    if not path.exists():
        return "—"
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    features = []
    checks = [
        ("<form", "نموذج"),
        ("<table", "جدول"),
        ("datatable", "جدول تفاعلي"),
        ("modal", "نافذة منبثقة"),
        ("export", "تصدير"),
        ("print", "طباعة"),
        ("chart", "رسم بياني"),
        ("search", "بحث"),
        ("filter", "تصفية"),
        ("select2", "اختيار متقدم"),
        ("dropzone", "رفع ملفات"),
    ]
    for needle, label in checks:
        if needle in text and label not in features:
            features.append(label)
    return "، ".join(features[:6]) or "عرض بيانات"


def sweep():
    result = {role: {} for role, *_ in USERS}
    for role, username, password, _label in USERS:
        with app.test_client() as c:
            c.post("/auth/login", data={"username": username, "password": password, "access_mode": "users"})
            for _ep, url in route_rows():
                if url in SIDE_EFFECT_URLS:
                    result[role][url] = "SKIP"
                    continue
                try:
                    resp = c.get(url)
                    code = resp.status_code
                except Exception as exc:
                    code = getattr(exc, "code", 500) or 500
                result[role][url] = code
                print(f"{role:10} {code} {url}", flush=True)
    Path(_CACHE_PATH).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> None:
    cache = Path(_CACHE_PATH)
    if cache.exists():
        access = json.loads(cache.read_text(encoding="utf-8"))
        print(f"Using cached sweep from {cache}")
    else:
        access = sweep()
    rows = route_rows()
    lines = [
        "# دليل الصفحات والصلاحيات — Page & Access Matrix",
        "",
        "تولّد هذا التقرير تلقائياً من خريطة المسارات الحية مع اختبار دخول فعلي لكل نوع مستخدم.",
        "",
        "## أنواع المستخدمين",
        "",
    ]
    for role, _u, _p, label in USERS:
        lines.append(f"- **{role}** — {label}")
    lines += [
        "",
        "## مفتاح الحالة",
        "",
        "- `200` — الصفحة متاحة؛ `302` — تحويل (مثلاً إلى لوحة التحكم)؛ "
        "`403` — مرفوض؛ `404` — غير موجود/مخفي؛ `500` — خطأ خادم (يجب أن لا يظهر).",
        "",
        "## ملخص الوصول",
        "",
        "| المستخدم | 200 | 302 | 403 | 404 | 301 | 500 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for role, _u, _p, label in USERS:
        codes = access[role]
        counts = {code: sum(1 for v in codes.values() if v == code) for code in (200, 302, 403, 404, 301, 500)}
        lines.append(
            f"| {role} ({label}) | {counts[200]} | {counts[302]} | {counts[403]} | "
            f"{counts[404]} | {counts[301]} | {counts[500]} |"
        )
    broken = sorted({url for role, *_ in USERS for url, code in access[role].items() if code == 500})
    lines += ["", "## صفحات بإخطار 500 (يجب أن تكون فارغة)", ""]
    lines += [f"- `{url}`" for url in broken] or ["- لا يوجد"]
    lines += [
        "",
        "## المصفوفة",
        "",
        "| الصفحة | المسار | الوظيفة | المزايا | مسموح | ممنوع | ملاحظات |",
        "|---|---|---|---|---|---|---|",
    ]
    for ep, url in rows:
        meta = page_meta(ep)
        title = PAGE_NAME_OVERRIDES.get(url) or arabic_title(meta["template"]) or meta["view"].replace("_", " ").title()
        function = MODULE_DESCRIPTIONS.get(meta["module"], meta["module"])
        allowed = [role for role, *_ in USERS if access[role].get(url) in (200, 302)]
        denied = [
            f"{role}({access[role].get(url, '?')})"
            for role, *_ in USERS
            if access[role].get(url, "?") not in (200, 302)
        ]
        decs = ", ".join(meta["decorators"]) or "—"
        features = template_features(meta["template"])
        note = f"وحدة: {meta['module']} · قيود: {decs}"
        if meta["template"]:
            note += f" · قالب: `{meta['template']}`"
        lines.append(
            f"| {title} | `{url}` | {function} | {features} | "
            f"{', '.join(allowed) or '—'} | {', '.join(denied) or '—'} | {note} |"
        )
    out = ROOT / "docs" / "PAGE_ACCESS_MATRIX.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {out} ({len(rows)} pages)")


if __name__ == "__main__":
    main()
