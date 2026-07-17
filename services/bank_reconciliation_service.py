"""
خدمة مطابقة البنك - Bank Reconciliation Service
"""

from decimal import Decimal
from datetime import timedelta
from extensions import db
from models import (
    BankReconciliation,
    BankReconciliationItem,
    BankStatementLine,
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    Cheque,
)
from utils.helpers import generate_number
from utils.gl_reference_types import GLRef


class BankReconciliationService:
    @staticmethod
    def create_reconciliation(
        bank_account_id,
        period_start,
        period_end,
        closing_balance_per_bank,
        created_by=None,
    ):
        """
        إنشاء مطابقة بنك جديدة
        """
        from flask_login import current_user

        from utils.tenanting import tenant_get_or_404

        bank_account = tenant_get_or_404(GLAccount, bank_account_id)

        # حساب رصيد الدفاتر
        from services.gl_service import GLService

        statement = GLService.get_account_statement(
            bank_account_id, date_from=None, date_to=period_end
        )

        closing_balance_per_books = Decimal(str(statement["closing_balance"]))
        opening_balance = Decimal(str(statement["opening_balance"]))

        # إنشاء المطابقة
        reconciliation_number = generate_number(
            "BR", BankReconciliation, "reconciliation_number"
        )

        reconciliation = BankReconciliation(
            tenant_id=bank_account.tenant_id,
            reconciliation_number=reconciliation_number,
            bank_account_id=bank_account_id,
            period_start=period_start,
            period_end=period_end,
            opening_balance_per_books=opening_balance,
            closing_balance_per_books=closing_balance_per_books,
            closing_balance_per_bank=closing_balance_per_bank,
            created_by=created_by
            or (current_user.id if current_user.is_authenticated else None),
        )

        db.session.add(reconciliation)
        db.session.flush()

        # جلب العمليات المعلقة تلقائياً
        BankReconciliationService._auto_populate_items(reconciliation)

        # حساب المطابقة
        reconciliation.calculate_reconciliation()
        try:
            db.session.flush()
        except Exception:
            raise

        return reconciliation

    @staticmethod
    def _auto_populate_items(reconciliation):
        """
        ملء العناصر تلقائياً (شيكات معلقة، عمليات غير مطابقة)
        """
        tid = getattr(reconciliation, "tenant_id", None)
        # 1. الشيكات الواردة المعلقة (pending, deposited)
        in_q = Cheque.query.filter(
            Cheque.cheque_type == "incoming",
            Cheque.status.in_(["pending", "deposited"]),
            Cheque.is_active,
            Cheque.due_date <= reconciliation.period_end,
        )
        if tid:
            in_q = in_q.filter(Cheque.tenant_id == tid)
        outstanding_cheques_in = in_q.all()

        for cheque in outstanding_cheques_in:
            item = BankReconciliationItem(
                tenant_id=tid,
                reconciliation_id=reconciliation.id,
                item_type="outstanding_deposit",
                transaction_date=cheque.issue_date,
                description=f"شيك وارد رقم {cheque.cheque_bank_number} - {cheque.drawer_name or ''}",
                amount=cheque.amount_aed,
                cheque_id=cheque.id,
            )
            db.session.add(item)
            reconciliation.outstanding_deposits += cheque.amount_aed

        # 2. الشيكات الصادرة المعلقة
        out_q = Cheque.query.filter(
            Cheque.cheque_type == "outgoing",
            Cheque.status.in_(["pending", "deposited"]),
            Cheque.is_active,
            Cheque.due_date <= reconciliation.period_end,
        )
        if tid:
            out_q = out_q.filter(Cheque.tenant_id == tid)
        outstanding_cheques_out = out_q.all()

        for cheque in outstanding_cheques_out:
            item = BankReconciliationItem(
                tenant_id=tid,
                reconciliation_id=reconciliation.id,
                item_type="outstanding_withdrawal",
                transaction_date=cheque.issue_date,
                description=f"شيك صادر رقم {cheque.cheque_bank_number} - {cheque.payee_name or ''}",
                amount=cheque.amount_aed,
                cheque_id=cheque.id,
            )
            db.session.add(item)
            reconciliation.outstanding_withdrawals += cheque.amount_aed

    @staticmethod
    def add_bank_charge(reconciliation_id, amount, description, transaction_date=None):
        """
        إضافة مصروف بنكي
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)

        if reconciliation.status != "draft":
            raise ValueError("لا يمكن تعديل مطابقة معتمدة")

        item = BankReconciliationItem(
            tenant_id=reconciliation.tenant_id,
            reconciliation_id=reconciliation_id,
            item_type="bank_charge",
            transaction_date=transaction_date or reconciliation.period_end,
            description=description,
            amount=abs(Decimal(str(amount))),
        )
        db.session.add(item)

        reconciliation.bank_charges += abs(Decimal(str(amount)))
        reconciliation.calculate_reconciliation()

        try:
            db.session.flush()
        except Exception:
            raise

        return item

    @staticmethod
    def add_bank_interest(
        reconciliation_id, amount, description, transaction_date=None
    ):
        """
        إضافة فائدة بنكية
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)

        if reconciliation.status != "draft":
            raise ValueError("لا يمكن تعديل مطابقة معتمدة")

        item = BankReconciliationItem(
            tenant_id=reconciliation.tenant_id,
            reconciliation_id=reconciliation_id,
            item_type="bank_interest",
            transaction_date=transaction_date or reconciliation.period_end,
            description=description,
            amount=abs(Decimal(str(amount))),
        )
        db.session.add(item)

        reconciliation.bank_interest += abs(Decimal(str(amount)))
        reconciliation.calculate_reconciliation()

        try:
            db.session.flush()
        except Exception:
            raise

        return item

    @staticmethod
    def complete_reconciliation(reconciliation_id):
        """
        إكمال المطابقة وإنشاء القيود التسوية
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)

        if reconciliation.status != "draft":
            raise ValueError("المطابقة معتمدة مسبقاً")

        # التحقق من التوازن
        result = reconciliation.calculate_reconciliation()

        if not result["is_balanced"]:
            raise ValueError(f"المطابقة غير متوازنة - الفرق: {result['difference']}")

        # إنشاء قيود التسوية

        lines = []

        # مصاريف بنكية
        if reconciliation.bank_charges > 0:
            lines.append(
                {
                    "account": "6950",  # مصاريف بنكية
                    "concept_code": "BANK_FEES",
                    "debit": reconciliation.bank_charges,
                    "credit": 0,
                    "description": "مصاريف بنكية",
                }
            )
            lines.append(
                {
                    "account": str(reconciliation.bank_account.code),  # البنك
                    "concept_code": "BANK",
                    "debit": 0,
                    "credit": reconciliation.bank_charges,
                    "description": "مصاريف بنكية",
                }
            )

        # فوائد بنكية
        if reconciliation.bank_interest > 0:
            lines.append(
                {
                    "account": str(reconciliation.bank_account.code),  # البنك
                    "concept_code": "BANK",
                    "debit": reconciliation.bank_interest,
                    "credit": 0,
                    "description": "فوائد بنكية",
                }
            )
            lines.append(
                {
                    "account": "4500",  # إيرادات أخرى
                    "concept_code": "BANK_INTEREST_INCOME",
                    "debit": 0,
                    "credit": reconciliation.bank_interest,
                    "description": "فوائد بنكية",
                }
            )

        if lines:
            from services.gl_posting import post_or_fail

            post_or_fail(
                lines=lines,
                description=f"قيد تسوية بنك - {reconciliation.reconciliation_number}",
                reference_type=GLRef.BANK_RECONCILIATION,
                reference_id=reconciliation.id,
                branch_id=getattr(reconciliation, "branch_id", None),
                tenant_id=getattr(reconciliation.bank_account, "tenant_id", None),
            )

        # تحديث الحالة
        reconciliation.status = "completed"

        try:
            db.session.flush()
        except Exception:
            raise

        return reconciliation

    @staticmethod
    def get_reconciliation_summary(bank_account_id, period_start, period_end):
        """
        ملخص المطابقة قبل الإنشاء
        """
        from services.gl_service import GLService
        from utils.tenanting import tenant_get_or_404

        bank_account = tenant_get_or_404(GLAccount, bank_account_id)
        tid = bank_account.tenant_id

        statement = GLService.get_account_statement(
            bank_account_id, date_from=period_start, date_to=period_end
        )

        in_q = Cheque.query.filter(
            Cheque.cheque_type == "incoming",
            Cheque.status.in_(["pending", "deposited"]),
            Cheque.is_active,
            Cheque.due_date.between(period_start, period_end),
        )
        if tid:
            in_q = in_q.filter(Cheque.tenant_id == tid)
        outstanding_cheques_in = in_q.all()

        out_q = Cheque.query.filter(
            Cheque.cheque_type == "outgoing",
            Cheque.status.in_(["pending", "deposited"]),
            Cheque.is_active,
            Cheque.due_date.between(period_start, period_end),
        )
        if tid:
            out_q = out_q.filter(Cheque.tenant_id == tid)
        outstanding_cheques_out = out_q.all()

        outstanding_deposits = sum(c.amount_aed for c in outstanding_cheques_in)
        outstanding_withdrawals = sum(c.amount_aed for c in outstanding_cheques_out)

        return {
            "closing_balance_per_books": statement["closing_balance"],
            "outstanding_deposits_count": len(outstanding_cheques_in),
            "outstanding_deposits_amount": float(outstanding_deposits),
            "outstanding_withdrawals_count": len(outstanding_cheques_out),
            "outstanding_withdrawals_amount": float(outstanding_withdrawals),
            "outstanding_cheques_in": outstanding_cheques_in,
            "outstanding_cheques_out": outstanding_cheques_out,
        }

    # ------------------------------------------------------------------
    # Auto-matching with GL lines and Bank Statement Lines (Odoo-style)
    # ------------------------------------------------------------------

    @staticmethod
    def auto_match_gl_lines(
        tenant_id,
        bank_account_id,
        period_start,
        period_end,
        amount_tolerance=Decimal("0.01"),
        date_tolerance_days=3,
    ):
        """
        Auto-match bank transactions to GL journal lines (payments, transfers).
        Odoo-style: exact amount + date proximity.
        Returns list of proposed matches.
        """
        from decimal import Decimal

        # Find un-matched GL lines affecting the bank account within the period
        gl_lines = (
            db.session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(
                GLJournalLine.account_id == bank_account_id,
                GLJournalEntry.entry_date.between(period_start, period_end),
                GLJournalEntry.tenant_id == tenant_id,
                GLJournalEntry.is_posted,
            )
            .all()
        )

        # Find un-matched bank statement lines
        stmt_lines = BankStatementLine.query.filter(
            BankStatementLine.tenant_id == tenant_id,
            BankStatementLine.bank_account_id == bank_account_id,
            BankStatementLine.transaction_date.between(period_start, period_end),
            BankStatementLine.status.in_(["imported", "suggested_match"]),
        ).all()

        matches = []
        matched_stmt_ids = set()
        matched_gl_ids = set()

        for stmt in stmt_lines:
            stmt_amount = Decimal(str(stmt.amount))
            for gl in gl_lines:
                if gl.id in matched_gl_ids:
                    continue
                gl_amount = Decimal(str(gl.debit or 0)) - Decimal(str(gl.credit or 0))
                # Match by exact amount
                if abs(stmt_amount - gl_amount) <= amount_tolerance:
                    # Check date proximity
                    gl_date = gl.entry.entry_date if gl.entry else stmt.transaction_date
                    date_diff = abs((stmt.transaction_date - gl_date).days)
                    if date_diff <= date_tolerance_days:
                        match_type = (
                            "exact"
                            if abs(stmt_amount - gl_amount) < Decimal("0.001")
                            else "amount_date"
                        )
                        matches.append(
                            {
                                "statement_line_id": stmt.id,
                                "journal_line_id": gl.id,
                                "match_type": match_type,
                                "amount_diff": float(abs(stmt_amount - gl_amount)),
                                "date_diff": date_diff,
                            }
                        )
                        matched_stmt_ids.add(stmt.id)
                        matched_gl_ids.add(gl.id)
                        break

        return matches

    @staticmethod
    def import_bank_statement(
        tenant_id, bank_account_id, csv_rows, statement_date=None
    ):
        """
        Import bank statement lines from CSV.
        csv_rows: list of dicts with keys: date, reference, description, amount
        Returns count of imported lines.
        """
        from datetime import datetime

        count = 0
        for row in csv_rows:
            line = BankStatementLine(
                tenant_id=tenant_id,
                bank_account_id=bank_account_id,
                statement_date=statement_date or datetime.now().date(),
                transaction_date=row.get("date"),
                reference=row.get("reference", "")[:120],
                description=row.get("description", "")[:255],
                amount=Decimal(str(row.get("amount", 0))),
                currency=row.get("currency", "AED"),
                raw_data=str(row),
            )
            db.session.add(line)
            count += 1
        db.session.flush()
        return count

    # ------------------------------------------------------------------
    # Suspense-account routing for orphan bank statement lines
    # ------------------------------------------------------------------

    @staticmethod
    def match_transaction(
        tenant_id,
        bank_account_id,
        stmt_line_id,
        amount_tolerance=Decimal("0.01"),
        date_tolerance_days=3,
    ):
        """
        Attempt to uniquely pair a single bank statement line with a GL
        journal line.  Returns the match dict on success, or ``None`` if
        no unique match is found (caller should route to Suspense).
        """
        from decimal import Decimal as _D

        stmt = db.session.get(BankStatementLine, stmt_line_id)
        if (
            not stmt
            or stmt.tenant_id != tenant_id
            or stmt.bank_account_id != bank_account_id
            or stmt.status not in ("imported", "suggested_match")
        ):
            return None

        stmt_amount = _D(str(stmt.amount))

        gl_lines = (
            db.session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(
                GLJournalLine.account_id == bank_account_id,
                GLJournalEntry.entry_date.between(
                    stmt.transaction_date - timedelta(days=date_tolerance_days),
                    stmt.transaction_date + timedelta(days=date_tolerance_days),
                ),
                GLJournalEntry.tenant_id == tenant_id,
                GLJournalEntry.is_posted,
            )
            .all()
        )

        candidates = []
        for gl in gl_lines:
            gl_amount = _D(str(gl.debit or 0)) - _D(str(gl.credit or 0))
            if abs(stmt_amount - gl_amount) <= amount_tolerance:
                date_diff = abs((stmt.transaction_date - gl.entry.entry_date).days)
                candidates.append((date_diff, gl))

        if len(candidates) != 1:
            return None

        date_diff, gl = candidates[0]
        match_type = (
            "exact"
            if abs(stmt_amount - _D(str(gl.debit or 0)) - _D(str(gl.credit or 0)))
            < _D("0.001")
            else "amount_date"
        )
        return {
            "statement_line_id": stmt.id,
            "journal_line_id": gl.id,
            "match_type": match_type,
            "amount_diff": float(
                abs(stmt_amount - (_D(str(gl.debit or 0)) - _D(str(gl.credit or 0))))
            ),
            "date_diff": date_diff,
        }

    @staticmethod
    def route_orphans_to_suspense(
        tenant_id,
        bank_account_id,
        period_start,
        period_end,
        description_prefix="Unmatched bank transaction",
    ):
        """
        Find all unmatched bank statement lines in the period and post a
        suspense GL entry for each, routing the unmapped amount to the
        Suspense account (concept code ``SUSPENSE``).

        Returns a list of dicts ``{statement_line_id, suspense_entry_id}``.
        """
        from decimal import Decimal as _D
        from services.gl_posting import post_or_fail, UnbalancedJournalEntryError
        from models import GLAccount

        orphans = BankStatementLine.query.filter(
            BankStatementLine.tenant_id == tenant_id,
            BankStatementLine.bank_account_id == bank_account_id,
            BankStatementLine.transaction_date.between(period_start, period_end),
            BankStatementLine.status.in_(["imported", "suggested_match"]),
        ).all()

        if not orphans:
            return []

        suspense_gl = (
            GLAccount.query.filter_by(
                tenant_id=tenant_id,
                type="liability",
            )
            .filter(GLAccount.code.like("2999%"))
            .first()
        )
        suspense_account_code = str(suspense_gl.code) if suspense_gl else "2999"

        results = []
        for stmt in orphans:
            amount = abs(_D(str(stmt.amount)))
            if amount <= _D("0.01"):
                stmt.status = "ignored"
                continue

            lines = [
                {
                    "account": (
                        str(stmt.bank_account.code)
                        if getattr(stmt, "bank_account", None)
                        and getattr(stmt.bank_account, "code", None)
                        else str(bank_account_id)
                    ),
                    "concept_code": "BANK",
                    "debit": amount if _D(str(stmt.amount)) > 0 else _D("0"),
                    "credit": _D("0") if _D(str(stmt.amount)) > 0 else amount,
                    "description": f"{description_prefix}: {stmt.description or stmt.reference or ''}",
                },
                {
                    "account": suspense_account_code,
                    "concept_code": "SUSPENSE",
                    "debit": _D("0") if _D(str(stmt.amount)) > 0 else amount,
                    "credit": amount if _D(str(stmt.amount)) > 0 else _D("0"),
                    "description": f"Suspense — {stmt.description or stmt.reference or 'orphan'}",
                },
            ]

            try:
                entry = post_or_fail(
                    lines=lines,
                    description=f"Suspense routing — {description_prefix} #{stmt.id}",
                    reference_type=GLRef.BANK_RECONCILIATION,
                    reference_id=stmt.id,
                    branch_id=None,
                    tenant_id=tenant_id,
                )
                stmt.status = "suggested_match"
                results.append(
                    {
                        "statement_line_id": stmt.id,
                        "suspense_entry_id": entry.id if hasattr(entry, "id") else None,
                    }
                )
            except (UnbalancedJournalEntryError, Exception):
                stmt.status = "ignored"

        try:
            db.session.flush()
        except Exception:
            raise

        return results

    @staticmethod
    def apply_matches(reconciliation_id, matches):
        """
        Apply proposed matches and create reconciliation items.
        matches: list of dicts from auto_match_gl_lines
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)
        if reconciliation.status != "draft":
            raise ValueError("لا يمكن تعديل مطابقة معتمدة")

        for m in matches:
            stmt = db.session.get(BankStatementLine, m["statement_line_id"])
            gl = db.session.get(GLJournalLine, m["journal_line_id"])
            if not stmt or not gl:
                continue

            stmt.status = "matched"
            stmt.match_type = m["match_type"]
            stmt.matched_journal_entry_id = gl.entry_id

            item = BankReconciliationItem(
                reconciliation_id=reconciliation_id,
                tenant_id=reconciliation.tenant_id,
                item_type="cleared",
                transaction_date=stmt.transaction_date,
                description=f"مطابق: {stmt.reference} - {stmt.description}",
                amount=abs(Decimal(str(stmt.amount))),
                journal_entry_id=gl.entry_id,
                is_cleared=True,
                cleared_date=stmt.transaction_date,
            )
            db.session.add(item)

        reconciliation.calculate_reconciliation()
        try:
            db.session.flush()
        except Exception:
            raise
        return reconciliation
