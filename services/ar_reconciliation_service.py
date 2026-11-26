"""Operational vs GL reconciliation for receivable-related accounts."""

from __future__ import annotations

from decimal import Decimal

from flask_babel import lazy_gettext
from sqlalchemy import func

from extensions import db
from models import Customer, GLAccount, GLJournalEntry, GLJournalLine, Sale
from services.gl_account_resolver import GLMappingError
from services.gl_service import GLService
from utils.gl_tenant import scope_gl_accounts


def _get_receivable_concept_account(tenant_id=None, branch_id=None):
    """Get the receivable account code via concept resolution (mapping only)."""
    if tenant_id:
        return GLService.get_account_code_for_concept("AR", tenant_id=tenant_id, branch_id=branch_id)
    raise ValueError("tenant_id is required to resolve AR account")


def _get_partner_account(tenant_id=None, branch_id=None):
    """Get the partner current account code (None when the module is off)."""
    if tenant_id:
        try:
            return GLService.get_account_code_for_concept(
                "PARTNER_CURRENT_ACCOUNT", tenant_id=tenant_id, branch_id=branch_id
            )
        except GLMappingError:
            # The partners module is optional; tenants that never enabled it
            # have no mapping and must still be able to open this report.
            return None
    raise ValueError("tenant_id is required to resolve partner account")


def _get_merchant_account(tenant_id=None, branch_id=None):
    """Get the merchant current account code (None when the module is off)."""
    if tenant_id:
        try:
            return GLService.get_account_code_for_concept(
                "MERCHANT_CURRENT_ACCOUNT", tenant_id=tenant_id, branch_id=branch_id
            )
        except GLMappingError:
            return None
    raise ValueError("tenant_id is required to resolve merchant account")


# These are the canonical subledger account codes — resolved dynamically per tenant/branch.
# Kept as callables so callers can pass tenant/branch context.
def _ar_subledger_accounts(tenant_id=None, branch_id=None):
    candidates = (
        (_get_receivable_concept_account(tenant_id, branch_id), lazy_gettext("ذمم مدينة"), ("regular",)),
        (_get_partner_account(tenant_id, branch_id), lazy_gettext("جاري الشركاء"), ("partner",)),
        (_get_merchant_account(tenant_id, branch_id), lazy_gettext("ذمم التجار"), ("merchant",)),
    )
    return tuple(row for row in candidates if row[0])


class ARReconciliationService:
    @staticmethod
    def _gl_balance(account_id: int, tenant_id: int | None, branch_id: int | None) -> Decimal:
        debit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.debit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.is_posted)
        )
        credit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.credit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.is_posted)
        )
        if tenant_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            credit_q = credit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.branch_id == branch_id)
            credit_q = credit_q.filter(GLJournalEntry.branch_id == branch_id)
        return Decimal(str(debit_q.scalar() or 0)) - Decimal(str(credit_q.scalar() or 0))

    @staticmethod
    def _ops_unpaid(tenant_id: int | None, branch_id: int | None, customer_types: tuple[str, ...]) -> Decimal:
        from models import Payment
        from models.receipt import Receipt

        customer_ids_q = db.session.query(Customer.id).filter(Customer.customer_type.in_(customer_types))
        if tenant_id is not None:
            customer_ids_q = customer_ids_q.filter(Customer.tenant_id == int(tenant_id))

        # القاعدة موحّدة مع الكشوفات ودفتر الأستاذ: الدفعة المؤكدة تؤثر،
        # والشيك المعلق يؤثر فوراً (Dr شيكات تحت التحصيل / Cr ذمم)،
        # والمرفوض (مرتد) لا أثر له.
        payment_effective = db.or_(
            Payment.payment_confirmed,
            db.and_(Payment.payment_method == "cheque", Payment.rejection_reason.is_(None)),
        )
        receipt_effective = db.or_(
            Receipt.payment_confirmed,
            db.and_(Receipt.payment_method == "cheque", Receipt.rejection_reason.is_(None)),
        )

        # سندات القبض تُخصم مرة واحدة فقط (ليست لكل فاتورة)، ويُستثنى منها ما
        # وزّع فعلياً على فواتير عبر دفعات مرتبطة تحمل رقم السند كمرجع.
        refs_q = db.session.query(Payment.reference_number).filter(
            Payment.reference_number.isnot(None),
            Payment.direction == "incoming",
            Payment.customer_id.in_(customer_ids_q),
            payment_effective,
        )
        if tenant_id is not None:
            refs_q = refs_q.filter(Payment.tenant_id == int(tenant_id))
        if branch_id is not None:
            refs_q = refs_q.filter(Payment.branch_id == branch_id)

        receipts_q = db.session.query(func.coalesce(func.sum(Receipt.amount_aed), 0)).filter(
            Receipt.customer_id.in_(customer_ids_q),
            receipt_effective,
            Receipt.receipt_number.notin_(refs_q),
        )
        if tenant_id is not None:
            receipts_q = receipts_q.filter(Receipt.tenant_id == int(tenant_id))
        if branch_id is not None:
            receipts_q = receipts_q.filter(Receipt.branch_id == branch_id)

        unallocated_receipts = Decimal(str(receipts_q.scalar() or 0))

        # Group effective incoming payments by sale once, then LEFT JOIN onto
        # the same sales. This replaces the per-sale SUM query (N+1) while
        # keeping the aggregation in base currency (amount_aed), Decimal-exact.
        payments_by_sale = db.session.query(
            Payment.sale_id.label("sale_id"),
            func.coalesce(func.sum(Payment.amount_aed), 0).label("paid_aed"),
        ).filter(
            Payment.sale_id.isnot(None),
            payment_effective,
            Payment.direction == "incoming",
        )
        if tenant_id is not None:
            payments_by_sale = payments_by_sale.filter(Payment.tenant_id == int(tenant_id))
        if branch_id is not None:
            payments_by_sale = payments_by_sale.filter(Payment.branch_id == branch_id)
        payments_by_sale = payments_by_sale.group_by(Payment.sale_id).subquery()

        sales_with_paid = (
            db.session.query(
                Sale.amount_aed.label("amount_aed"),
                func.coalesce(payments_by_sale.c.paid_aed, 0).label("paid_aed"),
            )
            .join(Customer, Sale.customer_id == Customer.id)
            .outerjoin(payments_by_sale, payments_by_sale.c.sale_id == Sale.id)
            .filter(
                Sale.status == "confirmed",
                Sale.is_active,
                Customer.customer_type.in_(customer_types),
            )
        )
        if tenant_id is not None:
            sales_with_paid = sales_with_paid.filter(Sale.tenant_id == int(tenant_id))
        if branch_id is not None:
            sales_with_paid = sales_with_paid.filter(Sale.branch_id == branch_id)

        total_unpaid = Decimal("0")
        for amount_aed, paid_aed in sales_with_paid.all():
            due = Decimal(str(amount_aed or 0)) - Decimal(str(paid_aed or 0))
            if due > Decimal("0"):
                total_unpaid += due

        total_unpaid -= unallocated_receipts
        return max(total_unpaid, Decimal("0"))

    @staticmethod
    def build_report(tenant_id: int | None = None, branch_id: int | None = None) -> dict:
        rows = []
        total_gl = Decimal("0")
        total_ops = Decimal("0")

        subledger_accounts = _ar_subledger_accounts(tenant_id, branch_id)

        for code, label, customer_types in subledger_accounts:
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
                    "matched": abs(diff) <= Decimal("0.01"),
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
                "receivable": _get_receivable_concept_account(tenant_id, branch_id),
                "partners": _get_partner_account(tenant_id, branch_id),
                "merchants": _get_merchant_account(tenant_id, branch_id),
            },
        }
