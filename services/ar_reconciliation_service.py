"""Operational vs GL reconciliation for receivable-related accounts."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models import Customer, GLAccount, GLJournalEntry, GLJournalLine, Sale
from services.gl_service import GL_ACCOUNTS
from utils.gl_tenant import scope_gl_accounts

AR_SUBLEDGER_ACCOUNTS = (
    ("1130", "ذمم مدينة", ("regular",)),
    ("3350", "جاري الشركاء", ("partner",)),
    ("2115", "ذمم التجار", ("merchant",)),
)


class ARReconciliationService:
    @staticmethod
    def _gl_balance(
        account_id: int, tenant_id: int | None, branch_id: int | None
    ) -> Decimal:
        debit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.debit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted == True)
        )
        credit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.credit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted == True)
        )
        if tenant_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            credit_q = credit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.branch_id == branch_id)
            credit_q = credit_q.filter(GLJournalEntry.branch_id == branch_id)
        return Decimal(str(debit_q.scalar() or 0)) - Decimal(
            str(credit_q.scalar() or 0)
        )

    @staticmethod
    def _ops_unpaid(
        tenant_id: int | None, branch_id: int | None, customer_types: tuple[str, ...]
    ) -> Decimal:
        from models import Payment, Receipt

        # Get all confirmed sales for these customer types
        sales_q = (
            db.session.query(Sale.id, Sale.amount_aed, Sale.customer_id)
            .join(Customer, Sale.customer_id == Customer.id)
            .filter(
                Sale.status == "confirmed",
                Sale.is_active == True,
                Customer.customer_type.in_(customer_types),
            )
        )
        if tenant_id is not None:
            sales_q = sales_q.filter(Sale.tenant_id == int(tenant_id))
        if branch_id is not None:
            sales_q = sales_q.filter(Sale.branch_id == branch_id)

        total_unpaid = Decimal("0")
        for sale_id, amount_aed, customer_id in sales_q.all():
            confirmed_payments = db.session.query(
                func.coalesce(func.sum(Payment.amount_aed), 0)
            ).filter(
                Payment.sale_id == sale_id,
                Payment.payment_confirmed == True,
                Payment.direction == "incoming",
            )
            confirmed_receipts = db.session.query(
                func.coalesce(func.sum(Receipt.amount_aed), 0)
            ).filter(
                Receipt.customer_id == customer_id,
                Receipt.payment_confirmed == True,
            )
            if tenant_id is not None:
                confirmed_payments = confirmed_payments.filter(
                    Payment.tenant_id == int(tenant_id)
                )
                confirmed_receipts = confirmed_receipts.filter(
                    Receipt.tenant_id == int(tenant_id)
                )
            if branch_id is not None:
                confirmed_payments = confirmed_payments.filter(
                    Payment.branch_id == branch_id
                )
                confirmed_receipts = confirmed_receipts.filter(
                    Receipt.branch_id == branch_id
                )

            paid = Decimal(str(confirmed_payments.scalar() or 0)) + Decimal(
                str(confirmed_receipts.scalar() or 0)
            )
            due = Decimal(str(amount_aed or 0)) - paid
            if due > Decimal("0"):
                total_unpaid += due

        return total_unpaid

    @staticmethod
    def build_report(
        tenant_id: int | None = None, branch_id: int | None = None
    ) -> dict:
        rows = []
        total_gl = Decimal("0")
        total_ops = Decimal("0")

        for code, label, customer_types in AR_SUBLEDGER_ACCOUNTS:
            acc_q = GLAccount.query.filter_by(code=code)
            if tenant_id is not None:
                acc_q = scope_gl_accounts(acc_q, tenant_id=tenant_id)
            account = acc_q.first()
            gl_bal = (
                ARReconciliationService._gl_balance(account.id, tenant_id, branch_id)
                if account
                else Decimal("0")
            )
            ops_bal = ARReconciliationService._ops_unpaid(
                tenant_id, branch_id, customer_types
            )
            diff = gl_bal - ops_bal
            rows.append(
                {
                    "code": code,
                    "label": label,
                    "gl_balance": float(gl_bal),
                    "ops_balance": float(ops_bal),
                    "difference": float(diff),
                    "matched": abs(diff) <= Decimal("1.00"),
                }
            )
            total_gl += gl_bal
            total_ops += ops_bal

        return {
            "rows": rows,
            "total_gl": float(total_gl),
            "total_ops": float(total_ops),
            "total_difference": float(total_gl - total_ops),
            "all_matched": all(r["matched"] for r in rows),
            "account_codes": {
                "receivable": GL_ACCOUNTS["receivable"],
                "partners": "3350",
                "merchants": GL_ACCOUNTS["merchants_payable"],
            },
        }
