"""
Read-only post-remediation database verification (GL + Phase 2 tenant integrity).

QA / pre-deploy only. SELECT queries; no writes. Uses DATABASE_URL from .env;
does not embed or print credentials.

Exit 0 = all critical checks pass (warnings may remain).
Exit 1 = one or more critical checks failed.

Run: python tools/qa/gl_remediation_verify.py [--profile local|production-readiness]

In production-readiness mode, test leftovers are treated as CRITICAL.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"

from sqlalchemy import create_engine, text

CRITICAL_CHECKS = {
    "cross_tenant_gl_lines": """
        SELECT COUNT(*) FROM gl_journal_lines jl
        JOIN gl_journal_entries je ON je.id = jl.entry_id
        JOIN gl_accounts ga ON ga.id = jl.account_id
        WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
    """,
    "journal_entries_without_lines": """
        SELECT COUNT(*) FROM gl_journal_entries je
        WHERE NOT EXISTS (SELECT 1 FROM gl_journal_lines jl WHERE jl.entry_id = je.id)
    """,
    "unbalanced_journal_entries": """
        SELECT COUNT(*) FROM (
          SELECT je.id FROM gl_journal_entries je
          JOIN gl_journal_lines jl ON jl.entry_id = je.id
          GROUP BY je.id HAVING ABS(SUM(jl.debit) - SUM(jl.credit)) > 0.001
        ) x
    """,
    "product_partners_tenant_null": "SELECT COUNT(*) FROM product_partners WHERE tenant_id IS NULL",
    "employees_tenant_null": "SELECT COUNT(*) FROM employees WHERE tenant_id IS NULL",
    "salary_advances_tenant_null": "SELECT COUNT(*) FROM salary_advances WHERE tenant_id IS NULL",
    "payroll_transactions_tenant_null": "SELECT COUNT(*) FROM payroll_transactions WHERE tenant_id IS NULL",
    "active_invoice_settings_tenant_null": """
        SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true
    """,
    "products_tenant_null": "SELECT COUNT(*) FROM products WHERE tenant_id IS NULL",
    "product_categories_tenant_null": "SELECT COUNT(*) FROM product_categories WHERE tenant_id IS NULL",
}

WARN_CHECKS = {
    "test_store_leftovers": """
        SELECT COUNT(*) FROM customers
        WHERE name ILIKE '%[TEST-STORE]%' OR name ILIKE '%TEST-STORE%'
    """,
    "uat_test_leftovers": """
        SELECT COUNT(*) FROM customers
        WHERE name ILIKE '%[UAT-TEST]%' OR name ILIKE '%UAT-TEST%'
           OR name ILIKE '%UAT-2-TMP%'
    """,
    "invoice_settings_tenant_null_total": (
        "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL"
    ),
    "users_tenant_null": "SELECT COUNT(*) FROM users WHERE tenant_id IS NULL",
    "users_tenant_null_not_global": """
        SELECT COUNT(*) FROM users u
        LEFT JOIN roles r ON r.id = u.role_id
        WHERE u.tenant_id IS NULL
          AND u.is_owner = false
          AND COALESCE(r.slug, '') NOT IN ('developer')
    """,
    "backup_tables_count": """
        SELECT COUNT(*) FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE '%backup%'
    """,
    "test_tenants_active": """
        SELECT COUNT(*) FROM tenants
        WHERE slug IN ('t-aed', 't-usd', 't-ils') AND is_active = true
    """,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="local", help="Check profile (local or production-readiness)")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    critical = {}
    warnings = {}
    with engine.connect() as conn:
        for name, sql in CRITICAL_CHECKS.items():
            critical[name] = conn.execute(text(sql)).scalar()
        for name, sql in WARN_CHECKS.items():
            warnings[name] = conn.execute(text(sql)).scalar()

    if args.profile == "production-readiness":
        if (warnings.get("test_store_leftovers") or 0) > 0:
            critical["test_store_leftovers"] = warnings["test_store_leftovers"]
            del warnings["test_store_leftovers"]
        if (warnings.get("uat_test_leftovers") or 0) > 0:
            critical["uat_test_leftovers"] = warnings["uat_test_leftovers"]
            del warnings["uat_test_leftovers"]

    critical_ok = all(v == 0 for v in critical.values())
    policy_fail = (warnings.get("users_tenant_null_not_global") or 0) > 0

    print(
        "DB_VERIFICATION_CRITICAL",
        critical,
        "OK" if critical_ok else "CRITICAL_FAIL",
    )
    print("DB_VERIFICATION_WARN", warnings)

    if not critical_ok or policy_fail:
        print("DB_VERIFICATION", "FAIL")
        return 1
    if any((warnings.get(k) or 0) > 0 for k in warnings):
        print("DB_VERIFICATION", "ALL_OK_WITH_WARNINGS")
    else:
        print("DB_VERIFICATION", "ALL_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
