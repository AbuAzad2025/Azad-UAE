"""
Phase 2A/2B/2C database remediation — transactional with backup tables.

QA / dev-staging only. Do NOT run against production without:
  - a full DB backup (pg_dump or equivalent),
  - explicit approval,
  - and verified rollback tables.

Performs targeted data remediation only (tenant backfill, invoice_settings deactivation).
Creates backup tables (*_backup_YYYYMMDD) before UPDATEs for rollback.
Does not DROP/TRUNCATE. Does not print secrets (uses .env DATABASE_URL locally).

Run: SKIP_SYSTEM_INTEGRITY=1 python scripts/maintenance/phase2_remediation_execute.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()


def main():
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    from sqlalchemy import text
    from extensions import db
    from app import create_app

    app = create_app()
    report = {"phase_2a": {}, "phase_2b": {}, "phase_2c": {}, "post_checks": {}, "errors": []}

    with app.app_context():
        def scalar(sql, params=None):
            return db.session.execute(text(sql), params or {}).fetchall()[0][0]

        def rows(sql, params=None):
            return [dict(r._mapping) for r in db.session.execute(text(sql), params or {})]

        # ========== Phase 2A PRE ==========
        report["phase_2a"]["pre"] = {
            "null_count": scalar("SELECT COUNT(*) FROM product_partners WHERE tenant_id IS NULL"),
            "conflict_count": scalar(
                """
                SELECT COUNT(*) FROM product_partners pp
                JOIN products p ON p.id = pp.product_id
                JOIN customers c ON c.id = pp.partner_customer_id
                WHERE pp.tenant_id IS NULL AND p.tenant_id IS NOT NULL AND c.tenant_id IS NOT NULL
                  AND p.tenant_id <> c.tenant_id
                """
            ),
            "sample_ids": [
                r["id"]
                for r in rows(
                    "SELECT id FROM product_partners WHERE tenant_id IS NULL ORDER BY id LIMIT 10"
                )
            ],
            "by_product_tenant": rows(
                """
                SELECT p.tenant_id, COUNT(*) cnt
                FROM product_partners pp JOIN products p ON p.id = pp.product_id
                WHERE pp.tenant_id IS NULL GROUP BY p.tenant_id
                """
            ),
        }

        # ========== Phase 2B PRE ==========
        report["phase_2b"]["pre"] = {
            "employees_null": scalar("SELECT COUNT(*) FROM employees WHERE tenant_id IS NULL"),
            "payroll_null": scalar("SELECT COUNT(*) FROM payroll_transactions WHERE tenant_id IS NULL"),
            "advances_null": scalar("SELECT COUNT(*) FROM salary_advances WHERE tenant_id IS NULL"),
            "branch_mapping": rows(
                """
                SELECT b.tenant_id, COUNT(*) cnt
                FROM employees e JOIN branches b ON b.id = e.branch_id
                WHERE e.tenant_id IS NULL GROUP BY b.tenant_id ORDER BY b.tenant_id
                """
            ),
        }

        # ========== Phase 2C PRE ==========
        report["phase_2c"]["pre"] = {
            "null_count": scalar("SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL"),
            "active_null_count": scalar(
                "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true"
            ),
            "by_tenant": rows(
                """
                SELECT tenant_id, COUNT(*) cnt, BOOL_OR(is_active) any_active
                FROM invoice_settings GROUP BY tenant_id ORDER BY tenant_id NULLS FIRST
                """
            ),
        }

        try:
            # --- 2A backup + update ---
            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS product_partners_backup_20260601 AS
                    SELECT id, tenant_id, product_id, partner_customer_id, percentage, created_at
                    FROM product_partners WHERE tenant_id IS NULL
                    """
                )
            )
            pp_updated = db.session.execute(
                text(
                    """
                    UPDATE product_partners pp
                    SET tenant_id = p.tenant_id
                    FROM products p
                    WHERE p.id = pp.product_id
                      AND pp.tenant_id IS NULL
                    """
                )
            ).rowcount
            report["phase_2a"]["backup_table"] = "product_partners_backup_20260601"
            report["phase_2a"]["updated_rows"] = pp_updated
            report["phase_2a"]["post"] = {
                "null_count": scalar("SELECT COUNT(*) FROM product_partners WHERE tenant_id IS NULL"),
                "conflict_count": scalar(
                    """
                    SELECT COUNT(*) FROM product_partners pp
                    JOIN products p ON p.id = pp.product_id
                    WHERE pp.tenant_id IS DISTINCT FROM p.tenant_id
                    """
                ),
            }

            # --- 2B backup + update ---
            for tbl, sql in [
                (
                    "employees_backup_20260601",
                    "CREATE TABLE IF NOT EXISTS employees_backup_20260601 AS SELECT id, tenant_id, branch_id FROM employees WHERE tenant_id IS NULL",
                ),
                (
                    "salary_advances_backup_20260601",
                    "CREATE TABLE IF NOT EXISTS salary_advances_backup_20260601 AS SELECT id, tenant_id, employee_id FROM salary_advances WHERE tenant_id IS NULL",
                ),
                (
                    "payroll_transactions_backup_20260601",
                    "CREATE TABLE IF NOT EXISTS payroll_transactions_backup_20260601 AS SELECT id, tenant_id, employee_id FROM payroll_transactions WHERE tenant_id IS NULL",
                ),
            ]:
                db.session.execute(text(sql))

            emp_updated = db.session.execute(
                text(
                    """
                    UPDATE employees e SET tenant_id = b.tenant_id
                    FROM branches b WHERE b.id = e.branch_id AND e.tenant_id IS NULL
                    """
                )
            ).rowcount
            adv_updated = db.session.execute(
                text(
                    """
                    UPDATE salary_advances sa SET tenant_id = e.tenant_id
                    FROM employees e WHERE e.id = sa.employee_id AND sa.tenant_id IS NULL
                    """
                )
            ).rowcount
            pay_updated = db.session.execute(
                text(
                    """
                    UPDATE payroll_transactions pt SET tenant_id = e.tenant_id
                    FROM employees e WHERE e.id = pt.employee_id AND pt.tenant_id IS NULL
                    """
                )
            ).rowcount

            report["phase_2b"]["backup_tables"] = [
                "employees_backup_20260601",
                "salary_advances_backup_20260601",
                "payroll_transactions_backup_20260601",
            ]
            report["phase_2b"]["updated_rows"] = {
                "employees": emp_updated,
                "salary_advances": adv_updated,
                "payroll_transactions": pay_updated,
            }
            report["phase_2b"]["post"] = {
                "employees_null": scalar("SELECT COUNT(*) FROM employees WHERE tenant_id IS NULL"),
                "payroll_null": scalar("SELECT COUNT(*) FROM payroll_transactions WHERE tenant_id IS NULL"),
                "advances_null": scalar("SELECT COUNT(*) FROM salary_advances WHERE tenant_id IS NULL"),
                "tenant_distribution": rows(
                    """
                    SELECT tenant_id, COUNT(*) cnt FROM employees GROUP BY tenant_id ORDER BY tenant_id
                    """
                ),
                "payroll_gl_entries": scalar(
                    "SELECT COUNT(*) FROM gl_journal_entries WHERE reference_type = 'Payroll'"
                ),
            }

            # --- 2C backup + deactivate ---
            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS invoice_settings_backup_20260601 AS
                    SELECT * FROM invoice_settings WHERE tenant_id IS NULL
                    """
                )
            )
            inv_deactivated = db.session.execute(
                text(
                    """
                    UPDATE invoice_settings
                    SET is_active = false
                    WHERE tenant_id IS NULL AND id >= 6
                    """
                )
            ).rowcount
            report["phase_2c"]["backup_table"] = "invoice_settings_backup_20260601"
            report["phase_2c"]["deactivated_rows"] = inv_deactivated
            report["phase_2c"]["post"] = {
                "null_count": scalar("SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL"),
                "active_null_count": scalar(
                    "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true"
                ),
                "tenant_settings_preserved": rows(
                    "SELECT id, tenant_id, is_active FROM invoice_settings WHERE id BETWEEN 1 AND 5 ORDER BY id"
                ),
                "get_active_by_tenant": {},
            }
            for tid in (1, 2, 3, 4, 5):
                row = rows(
                    """
                    SELECT id, tenant_id, is_active, company_name_en
                    FROM invoice_settings
                    WHERE tenant_id = :tid AND is_active = true
                    ORDER BY id LIMIT 1
                    """,
                    {"tid": tid},
                )
                report["phase_2c"]["post"]["get_active_by_tenant"][str(tid)] = row[0] if row else None

            # --- post checks ---
            report["post_checks"] = {
                "product_partners_null": scalar(
                    "SELECT COUNT(*) FROM product_partners WHERE tenant_id IS NULL"
                ),
                "employees_null": scalar("SELECT COUNT(*) FROM employees WHERE tenant_id IS NULL"),
                "salary_advances_null": scalar(
                    "SELECT COUNT(*) FROM salary_advances WHERE tenant_id IS NULL"
                ),
                "payroll_transactions_null": scalar(
                    "SELECT COUNT(*) FROM payroll_transactions WHERE tenant_id IS NULL"
                ),
                "active_invoice_settings_null": scalar(
                    "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true"
                ),
                "gl_cross_tenant": scalar(
                    """
                    SELECT COUNT(*) FROM gl_journal_lines jl
                    JOIN gl_journal_entries je ON je.id = jl.entry_id
                    JOIN gl_accounts ga ON ga.id = jl.account_id
                    WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
                    """
                ),
                "unbalanced_je": scalar(
                    """
                    SELECT COUNT(*) FROM (
                      SELECT je.id FROM gl_journal_entries je
                      JOIN gl_journal_lines jl ON jl.entry_id = je.id
                      GROUP BY je.id HAVING ABS(SUM(jl.debit)-SUM(jl.credit)) > 0.001
                    ) x
                    """
                ),
                "empty_je": scalar(
                    """
                    SELECT COUNT(*) FROM gl_journal_entries je
                    WHERE NOT EXISTS (SELECT 1 FROM gl_journal_lines jl WHERE jl.entry_id = je.id)
                    """
                ),
                "products_null": scalar("SELECT COUNT(*) FROM products WHERE tenant_id IS NULL"),
                "product_categories_null": scalar(
                    "SELECT COUNT(*) FROM product_categories WHERE tenant_id IS NULL"
                ),
            }

            db.session.commit()
            report["status"] = "committed"
        except Exception as exc:
            db.session.rollback()
            report["status"] = "rolled_back"
            report["errors"].append(str(exc))
            raise

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    checks = report.get("post_checks", {})
    ok = report.get("status") == "committed" and all(v == 0 for v in checks.values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
