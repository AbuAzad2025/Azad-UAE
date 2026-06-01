"""
Read-only post-remediation database verification (GL + Phase 2 tenant integrity).

QA tool only — SELECT queries; no writes. Uses DATABASE_URL from .env locally;
does not embed or print credentials.

Run: python tools/qa/gl_remediation_verify.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text

CHECKS = {
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
    "test_store_leftovers": """
        SELECT COUNT(*) FROM customers
        WHERE name ILIKE '%[TEST-STORE]%' OR name ILIKE '%TEST-STORE%'
    """,
    "uat_test_leftovers": """
        SELECT COUNT(*) FROM customers
        WHERE name ILIKE '%[UAT-TEST]%' OR name ILIKE '%UAT-TEST%'
           OR name ILIKE '%UAT-2-TMP%'
    """,
}


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    results = {}
    with engine.connect() as conn:
        for name, sql in CHECKS.items():
            results[name] = conn.execute(text(sql)).scalar()
    ok = all(v == 0 for v in results.values())
    print("DB_VERIFICATION", results, "ALL_OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
