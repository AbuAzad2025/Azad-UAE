"""
One-shot GL remediation (Phase 1B).
Run: SKIP_SYSTEM_INTEGRITY=1 python tools/qa/gl_remediation_execute.py
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

BACKUP_TABLE = "gl_remediation_backup_20260601"
EMPTY_ENTRY_IDS = (844, 848, 852, 856)
ENTRY_857_ID = 857


def _report(**kwargs):
    return kwargs


def main():
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    from app import create_app
    from extensions import db
    from sqlalchemy import text
    from models import Expense, ExpenseCategory, GLJournalEntry, GLJournalLine, Customer
    from services import gl_helpers

    app = create_app()
    report = {"steps": [], "errors": []}

    with app.app_context():
        conn = db.session.connection()

        # --- backup ---
        db.session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS
                SELECT jl.id, jl.entry_id, jl.account_id, jl.tenant_id, jl.debit, jl.credit, jl.description
                FROM gl_journal_lines jl
                WHERE jl.entry_id IN (
                    SELECT DISTINCT je.id FROM gl_journal_entries je
                    JOIN gl_journal_lines jl2 ON jl2.entry_id = je.id
                    JOIN gl_accounts ga ON ga.id = jl2.account_id
                    WHERE je.tenant_id IS NOT NULL AND je.tenant_id <> ga.tenant_id
                ) OR jl.entry_id = :e857
                """
            ),
            {"e857": ENTRY_857_ID},
        )
        backup_count = db.session.execute(text(f"SELECT COUNT(*) FROM {BACKUP_TABLE}")).scalar()
        report["steps"].append({"backup_table": BACKUP_TABLE, "lines_backed_up": backup_count})

        pre_cross = db.session.execute(
            text(
                """
                SELECT COUNT(*) FROM gl_journal_lines jl
                JOIN gl_journal_entries je ON je.id = jl.entry_id
                JOIN gl_accounts ga ON ga.id = jl.account_id
                WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
                """
            )
        ).scalar()
        report["pre_cross_tenant_lines"] = pre_cross

        # --- remap cross-tenant lines ---
        remapped = db.session.execute(
            text(
                """
                UPDATE gl_journal_lines jl
                SET account_id = m.new_account_id,
                    tenant_id  = m.tenant_id
                FROM (
                    SELECT jl2.id AS line_id,
                           tgt.id AS new_account_id,
                           je.tenant_id
                    FROM gl_journal_lines jl2
                    JOIN gl_journal_entries je ON je.id = jl2.entry_id
                    JOIN gl_accounts ga ON ga.id = jl2.account_id
                    JOIN gl_accounts tgt
                      ON tgt.tenant_id = je.tenant_id
                     AND tgt.code = ga.code
                     AND tgt.type = ga.type
                    WHERE je.tenant_id IS NOT NULL
                      AND ga.tenant_id IS NOT NULL
                      AND je.tenant_id <> ga.tenant_id
                ) m
                WHERE jl.id = m.line_id
                """
            )
        ).rowcount
        report["steps"].append({"remap_cross_tenant_lines": remapped})

        # --- fix entry 857 tenant ---
        db.session.execute(
            text("UPDATE gl_journal_entries SET tenant_id = 1 WHERE id = :id"),
            {"id": ENTRY_857_ID},
        )
        db.session.execute(
            text("UPDATE gl_journal_lines SET tenant_id = 1 WHERE entry_id = :id"),
            {"id": ENTRY_857_ID},
        )
        report["steps"].append({"fix_entry_857_tenant_id": 1})

        # --- fix empty expense journal entries ---
        expense_fixes = []
        for entry_id in EMPTY_ENTRY_IDS:
            entry = GLJournalEntry.query.get(entry_id)
            if not entry:
                expense_fixes.append({"entry_id": entry_id, "status": "missing"})
                continue
            line_count = GLJournalLine.query.filter_by(entry_id=entry_id).count()
            if line_count > 0:
                expense_fixes.append({"entry_id": entry_id, "status": "already_has_lines", "lines": line_count})
                continue
            expense = Expense.query.get(entry.reference_id) if entry.reference_type in ("Expense", "expense") else None
            if not expense:
                expense_fixes.append({"entry_id": entry_id, "status": "no_expense_ref"})
                continue

            tenant_id = expense.tenant_id or entry.tenant_id
            category = ExpenseCategory.query.get(expense.category_id)
            expense_code = (category.gl_account_code if category and category.gl_account_code else "6990")
            acc = gl_helpers.get_account(expense_code, tenant_id)
            if not acc or acc.is_header:
                expense_code = "6990"
                acc = gl_helpers.get_account(expense_code, tenant_id)
            if expense.payment_method == "cash":
                pay_code = "1110"
            elif expense.payment_method == "cheque":
                pay_code = "2110"
            else:
                pay_code = "1120"
            pay_acc = gl_helpers.get_account(pay_code, tenant_id)
            if not acc or not pay_acc:
                expense_fixes.append({"entry_id": entry_id, "status": "account_missing", "expense_id": expense.id})
                continue

            amount = Decimal(str(expense.amount))
            db.session.add(
                GLJournalLine(
                    tenant_id=tenant_id,
                    entry_id=entry.id,
                    account_id=acc.id,
                    debit=amount,
                    credit=Decimal("0"),
                    description=expense.description,
                    amount_aed=amount,
                )
            )
            db.session.add(
                GLJournalLine(
                    tenant_id=tenant_id,
                    entry_id=entry.id,
                    account_id=pay_acc.id,
                    debit=Decimal("0"),
                    credit=amount,
                    description=f"Payment {expense.payment_method}",
                    amount_aed=-amount,
                )
            )
            entry.total_debit = amount
            entry.total_credit = amount
            expense_fixes.append(
                {
                    "entry_id": entry_id,
                    "status": "lines_added",
                    "expense_id": expense.id,
                    "amount": str(amount),
                    "debit_code": expense_code,
                    "credit_code": pay_code,
                }
            )
        report["steps"].append({"empty_expense_entries": expense_fixes})

        # --- fix rounding imbalances (±0.001) ---
        rounding_rows = db.session.execute(
            text(
                """
                SELECT je.id, SUM(jl.debit) AS d, SUM(jl.credit) AS c
                FROM gl_journal_entries je
                JOIN gl_journal_lines jl ON jl.entry_id = je.id
                GROUP BY je.id
                HAVING ABS(SUM(jl.debit) - SUM(jl.credit)) BETWEEN 0.0001 AND 0.01
                """
            )
        ).fetchall()
        rounding_fixes = []
        for row in rounding_rows:
            entry_id, d, c = row[0], Decimal(str(row[1])), Decimal(str(row[2]))
            diff = d - c
            line = (
                GLJournalLine.query.filter_by(entry_id=entry_id)
                .order_by(GLJournalLine.id.desc())
                .first()
            )
            if not line:
                continue
            if diff > 0:
                line.credit = Decimal(str(line.credit or 0)) + diff
            else:
                line.debit = Decimal(str(line.debit or 0)) + abs(diff)
            entry = GLJournalEntry.query.get(entry_id)
            if entry:
                entry.total_debit = d if diff <= 0 else d
                entry.total_credit = c if diff <= 0 else c + diff if diff > 0 else c + abs(diff)
                # recompute from lines
                lines = GLJournalLine.query.filter_by(entry_id=entry_id).all()
                entry.total_debit = sum(Decimal(str(x.debit or 0)) for x in lines)
                entry.total_credit = sum(Decimal(str(x.credit or 0)) for x in lines)
            rounding_fixes.append({"entry_id": entry_id, "adjustment": str(diff), "line_id": line.id})
        report["steps"].append({"rounding_fixes": rounding_fixes})

        # --- remove test customer if orphan ---
        test_customer = Customer.query.get(118)
        test_customer_result = None
        if test_customer and "[TEST-STORE]" in (test_customer.name or ""):
            from models import Sale

            if Sale.query.filter_by(customer_id=118).count() == 0:
                db.session.delete(test_customer)
                test_customer_result = "deleted_id_118"
            else:
                test_customer_result = "kept_has_sales"
        report["steps"].append({"test_customer_118": test_customer_result})

        post_cross = db.session.execute(
            text(
                """
                SELECT COUNT(*) FROM gl_journal_lines jl
                JOIN gl_journal_entries je ON je.id = jl.entry_id
                JOIN gl_accounts ga ON ga.id = jl.account_id
                WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
                """
            )
        ).scalar()
        report["post_cross_tenant_lines"] = post_cross

        empty_remaining = db.session.execute(
            text(
                """
                SELECT COUNT(*) FROM gl_journal_entries je
                WHERE NOT EXISTS (SELECT 1 FROM gl_journal_lines jl WHERE jl.entry_id = je.id)
                """
            )
        ).scalar()
        report["post_entries_without_lines"] = empty_remaining

        db.session.commit()
        report["status"] = "committed"

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("post_cross_tenant_lines") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
