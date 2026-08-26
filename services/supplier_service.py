"""Supplier service — supplier creation and management."""

from __future__ import annotations

import logging
from typing import Any

from extensions import db

logger = logging.getLogger(__name__)


class SupplierService:
    """Pure business logic for supplier operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_supplier(
        name: str,
        phone: str = "",
        email: str = "",
        address: str = "",
        name_en: str = "",
        company_name: str = "",
        phone2: str = "",
        website: str = "",
        city: str = "",
        country: str = "PS",
        tax_number: str = "",
        commercial_registration: str = "",
        supplier_type: str = "individual",
        rating=None,
        credit_limit: float = 0,
        payment_terms_days: int = 30,
        preferred_currency: str = "AED",
        total_purchases_aed=None,
        total_paid_aed=None,
        notes: str = "",
        tags: str = "",
        is_verified: bool = False,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ):
        """Create a new supplier. Returns the created supplier (not yet committed)."""
        from models import Supplier

        supplier = Supplier(
            name=name,
            name_en=name_en,
            company_name=company_name,
            phone=phone,
            phone2=phone2,
            email=email,
            website=website,
            address=address,
            city=city,
            country=country,
            tax_number=tax_number,
            commercial_registration=commercial_registration,
            supplier_type=supplier_type,
            rating=rating,
            credit_limit=credit_limit,
            payment_terms_days=payment_terms_days,
            preferred_currency=preferred_currency,
            total_purchases_aed=total_purchases_aed or 0,
            total_paid_aed=total_paid_aed or 0,
            notes=notes,
            tags=tags,
            is_verified=is_verified,
            is_active=True,
            created_by=created_by,
        )
        if tenant_id is not None:
            supplier.tenant_id = tenant_id
        db.session.add(supplier)
        return supplier

    @staticmethod
    def scoped_suppliers_query(branch_id=None):
        """Tenant-scoped supplier query, optionally narrowed to suppliers active in a branch."""
        from sqlalchemy import select

        from models import Payment, Purchase, Supplier
        from utils.tenanting import tenant_query

        query = tenant_query(Supplier)
        if branch_id is None:
            return query

        purchase_ids = select(Purchase.supplier_id).where(
            Purchase.supplier_id.isnot(None),
            Purchase.branch_id == branch_id,
        )
        payment_ids = select(Payment.supplier_id).where(
            Payment.supplier_id.isnot(None),
            Payment.branch_id == branch_id,
        )
        return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))

    @staticmethod
    def supplier_in_branch_scope(supplier_id, branch_id=None):
        """True when no branch scope applies or the supplier has activity in the scoped branch."""
        if branch_id is None:
            return True
        scoped_query = SupplierService.scoped_suppliers_query(branch_id=branch_id)
        from models import Supplier

        return db.session.query(scoped_query.filter(Supplier.id == supplier_id).exists()).scalar()

    @staticmethod
    def supplier_scoped_totals(supplier_id, tenant_id=None, branch_id=None):
        """(confirmed purchases, total_purchases_aed, total_paid_outgoing_aed) within tenant/branch."""
        from models import Payment, Purchase

        purchases_query = Purchase.query.filter_by(supplier_id=supplier_id, status="confirmed", tenant_id=tenant_id)
        payments_query = Payment.query.filter_by(supplier_id=supplier_id, tenant_id=tenant_id)
        if branch_id is not None:
            purchases_query = purchases_query.filter(Purchase.branch_id == branch_id)
            payments_query = payments_query.filter(Payment.branch_id == branch_id)

        purchases = purchases_query.all()
        total_purchases = sum((p.amount_aed or 0) for p in purchases)
        total_paid = sum((p.amount_aed or 0) for p in payments_query.filter(Payment.direction == "outgoing").all())
        return purchases, total_purchases, total_paid

    @staticmethod
    def supplier_branch_labels(supplier_ids):
        """{supplier_id: [branch_label, ...]} aggregated from purchases/payments branches."""
        from models import Branch, Payment, Purchase

        branch_map: dict[Any, set[int]] = {sid: set() for sid in supplier_ids}

        purchase_rows = (
            db.session.query(Purchase.supplier_id, Purchase.branch_id)
            .filter(
                Purchase.supplier_id.in_(supplier_ids),
                Purchase.branch_id.isnot(None),
            )
            .all()
        )
        payment_rows = (
            db.session.query(Payment.supplier_id, Payment.branch_id)
            .filter(
                Payment.supplier_id.in_(supplier_ids),
                Payment.branch_id.isnot(None),
            )
            .all()
        )

        branch_ids = set()
        for sid, bid in purchase_rows + payment_rows:
            if sid in branch_map and bid:
                branch_map[sid].add(bid)
                branch_ids.add(bid)

        branches = Branch.query.filter(Branch.id.in_(branch_ids)).all() if branch_ids else []
        branch_labels = {b.id: (f"{b.name} ({b.code})" if getattr(b, "code", None) else b.name) for b in branches}

        return {
            sid: [branch_labels.get(bid, str(bid)) for bid in sorted(branch_map.get(sid, set()))]
            for sid in supplier_ids
        }

    @staticmethod
    def supplier_linked_counts(supplier_id, tenant_id=None, branch_id=None):
        """Counts of purchases/payments linked to a supplier within tenant/branch."""
        from models import Payment, Purchase

        purchases_query = Purchase.query.filter_by(supplier_id=supplier_id, tenant_id=tenant_id)
        payments_query = Payment.query.filter_by(supplier_id=supplier_id, tenant_id=tenant_id)
        if branch_id is not None:
            purchases_query = purchases_query.filter(Purchase.branch_id == branch_id)
            payments_query = payments_query.filter(Payment.branch_id == branch_id)
        return {"purchases": purchases_query.count(), "payments": payments_query.count()}

    @staticmethod
    def statement_ledger_queries(supplier_id, tenant_id=None, branch_id=None):
        """(payments_q, returns_q) for a supplier statement; payments include incoming refunds."""
        from models import Payment, PurchaseReturn

        payments_q = Payment.query.filter_by(supplier_id=supplier_id, tenant_id=tenant_id)
        returns_q = PurchaseReturn.query.filter_by(supplier_id=supplier_id, tenant_id=tenant_id)
        if branch_id is not None:
            payments_q = payments_q.filter(Payment.branch_id == branch_id)
            returns_q = returns_q.filter(PurchaseReturn.branch_id == branch_id)
        return payments_q, returns_q

    @staticmethod
    def print_statement_queries(supplier_id, tenant_id=None, branch_id=None):
        """(purchases_q, payments_q, returns_q) for the printable supplier statement."""
        from models import Purchase

        purchases_q = Purchase.query.filter_by(supplier_id=supplier_id, status="confirmed", tenant_id=tenant_id)
        if branch_id is not None:
            purchases_q = purchases_q.filter(Purchase.branch_id == branch_id)
        payments_q, returns_q = SupplierService.statement_ledger_queries(
            supplier_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
        )
        return purchases_q, payments_q, returns_q

    @staticmethod
    def preperiod_opening_balance(supplier_id, date_from, tenant_id=None, branch_id=None):
        """Statement opening balance for activity strictly before ``date_from``."""
        from sqlalchemy import func

        from models import Payment, Purchase, PurchaseReturn

        if not date_from:
            return 0.0

        pre_purchases_q = Purchase.query.filter(
            Purchase.supplier_id == supplier_id,
            Purchase.status == "confirmed",
            Purchase.tenant_id == tenant_id,
            func.date(Purchase.purchase_date) < date_from,
        )
        pre_payments_q = Payment.query.filter(
            Payment.supplier_id == supplier_id,
            Payment.tenant_id == tenant_id,
            func.date(Payment.payment_date) < date_from,
        )
        pre_returns_q = PurchaseReturn.query.filter(
            PurchaseReturn.supplier_id == supplier_id,
            PurchaseReturn.tenant_id == tenant_id,
            func.date(PurchaseReturn.return_date) < date_from,
        )
        if branch_id is not None:
            pre_purchases_q = pre_purchases_q.filter(Purchase.branch_id == branch_id)
            pre_payments_q = pre_payments_q.filter(Payment.branch_id == branch_id)
            pre_returns_q = pre_returns_q.filter(PurchaseReturn.branch_id == branch_id)

        opening_balance = float(
            pre_purchases_q.with_entities(func.coalesce(func.sum(Purchase.amount_aed), 0)).scalar() or 0
        )
        for pm in pre_payments_q.all():
            # A payment affects the balance when confirmed, or when it is a
            # still-pending cheque without a rejection reason.
            if not (pm.payment_confirmed or (pm.payment_method == "cheque" and not pm.rejection_reason)):
                continue
            amt = float(pm.amount_aed or 0)
            opening_balance += amt if pm.direction == "incoming" else -amt
        opening_balance -= float(
            pre_returns_q.with_entities(func.coalesce(func.sum(PurchaseReturn.amount_aed), 0)).scalar() or 0
        )
        return opening_balance
