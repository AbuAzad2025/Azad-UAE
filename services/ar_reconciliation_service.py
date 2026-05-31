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
    def _gl_balance(account_id: int, tenant_id: int | None, branch_id: int | None) -> Decimal:
        debit_q = db.session.query(func.coalesce(func.sum(GLJournalLine.debit), 0)).filter(
            GLJournalLine.account_id == account_id
        ).join(GLJournalEntry).filter(GLJournalEntry.is_posted == True)
        credit_q = db.session.query(func.coalesce(func.sum(GLJournalLine.credit), 0)).filter(
            GLJournalLine.account_id == account_id
        ).join(GLJournalEntry).filter(GLJournalEntry.is_posted == True)
        if tenant_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            credit_q = credit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.branch_id == branch_id)
            credit_q = credit_q.filter(GLJournalEntry.branch_id == branch_id)
        return Decimal(str(debit_q.scalar() or 0)) - Decimal(str(credit_q.scalar() or 0))

    @staticmethod
    def _ops_unpaid(tenant_id: int | None, branch_id: int | None, customer_types: tuple[str, ...]) -> Decimal:
        q = (
            db.session.query(func.coalesce(func.sum(Sale.amount_aed - Sale.paid_amount_aed), 0))
            .join(Customer, Sale.customer_id == Customer.id)
            .filter(
                Sale.status == "confirmed",
                Sale.is_active == True,
                Sale.amount_aed > Sale.paid_amount_aed,
                Customer.customer_type.in_(customer_types),
            )
        )
        if tenant_id is not None:
            q = q.filter(Sale.tenant_id == int(tenant_id))
        if branch_id is not None:
            q = q.filter(Sale.branch_id == branch_id)
        return Decimal(str(q.scalar() or 0))

    @staticmethod
    def build_report(tenant_id: int | None = None, branch_id: int | None = None) -> dict:
        rows = []
        total_gl = Decimal("0")
        total_ops = Decimal("0")

        for code, label, customer_types in AR_SUBLEDGER_ACCOUNTS:
            acc_q = GLAccount.query.filter_by(code=code)
            if tenant_id is not None:
                acc_q = scope_gl_accounts(acc_q, tenant_id=tenant_id)
            account = acc_q.first()
            gl_bal = ARReconciliationService._gl_balance(account.id, tenant_id, branch_id) if account else Decimal("0")
            ops_bal = ARReconciliationService._ops_unpaid(tenant_id, branch_id, customer_types)
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
