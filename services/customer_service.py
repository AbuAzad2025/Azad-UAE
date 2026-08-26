"""Customer service — balance operations and customer management."""

from __future__ import annotations

import logging
from typing import Any

from extensions import db
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)


class CustomerService:
    """Pure business logic for customer operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_customer(
        name: str,
        name_ar: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        email: str | None = None,
        tax_number: str | None = None,
        preferred_currency: str = "AED",
        customer_type: str = "individual",
        is_active: bool = True,
        notes: str | None = None,
        tenant_id: int | None = None,
    ):
        """Create a new customer. Returns the created customer (not yet committed)."""
        from models.customer import Customer

        customer = Customer(
            name=name,
            name_ar=name_ar or "",
            phone=phone or "",
            address=address or "",
            email=email or "",
            tax_number=tax_number or "",
            preferred_currency=preferred_currency,
            customer_type=customer_type,
            is_active=is_active,
            notes=notes or "",
            balance=0,
        )
        if tenant_id is not None:
            customer.tenant_id = tenant_id
        db.session.add(customer)
        return customer

    @staticmethod
    def set_balance(customer_id: int, new_balance_aed, tenant_id: int):
        """Set a customer's balance directly (correction/admin operations)."""
        from models.customer import Customer

        customer = tenant_query(Customer).filter_by(id=customer_id, tenant_id=tenant_id).first()
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found in tenant {tenant_id}")
        customer.set_balance(new_balance_aed)
        db.session.flush()
        return customer.balance

    @staticmethod
    def adjust_balance(customer_id: int, delta_aed, tenant_id: int):
        """Adjust a customer's balance by delta (positive = credit, negative = debit)."""
        from models.customer import Customer

        customer = tenant_query(Customer).filter_by(id=customer_id, tenant_id=tenant_id).first()
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found in tenant {tenant_id}")
        customer.adjust_balance(delta_aed)
        db.session.flush()
        return customer.balance

    @staticmethod
    def list_active_paginated(tid, page, per_page):
        """Active customers ordered by name, tenant-scoped, optimized pagination."""
        from models import Customer

        query = Customer.query.filter_by(is_active=True)
        if tid:
            query = query.filter(Customer.tenant_id == tid)
        query = query.order_by(Customer.name)

        from utils.query_optimizer import paginate_optimized

        return paginate_optimized(query, page=page, per_page=per_page)

    @staticmethod
    def get_tenant_customer(customer_id, tenant_id):
        """Fetch a customer by id within a tenant; returns None when absent."""
        from models import Customer

        return Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()

    @staticmethod
    def customer_id_in_branch_scope(customer_id, branch_id):
        """True when the customer has transactions recorded under *branch_id*."""
        from sqlalchemy import select

        from models import Customer, Payment, Sale
        from models.receipt import Receipt

        sale_ids = select(Sale.customer_id).where(
            Sale.customer_id.isnot(None),
            Sale.branch_id == branch_id,
        )
        payment_ids = select(Payment.customer_id).where(
            Payment.customer_id.isnot(None),
            Payment.branch_id == branch_id,
        )
        receipt_ids = select(Receipt.customer_id).where(
            Receipt.customer_id.isnot(None),
            Receipt.branch_id == branch_id,
        )
        scoped = tenant_query(Customer).filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))
        return db.session.query(scoped.filter(Customer.id == customer_id).exists()).scalar()

    @staticmethod
    def get_unpaid_sales(customer_id, branch_id=None):
        """Confirmed sales with a remaining balance, optionally branch-scoped."""
        from models import Sale

        query = Sale.query.filter(
            Sale.customer_id == customer_id,
            Sale.status == "confirmed",
            Sale.balance_due > 0,
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.order_by(Sale.sale_date.asc()).all()

    @staticmethod
    def recent_sales(customer_id, tenant_id, branch_id=None, limit=20):
        """Most recent sales for a customer, newest first."""
        from models import Sale

        sales = Sale.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        if branch_id is not None:
            sales = sales.filter(Sale.branch_id == branch_id)
        return sales.order_by(Sale.sale_date.desc()).limit(limit).all()

    @staticmethod
    def confirmed_sales(customer_id, branch_id=None):
        """All confirmed sales for a customer, optionally branch-scoped."""
        from models import Sale

        sales = Sale.query.filter_by(customer_id=customer_id, status="confirmed")
        if branch_id is not None:
            sales = sales.filter(Sale.branch_id == branch_id)
        return sales.order_by(Sale.sale_date.desc()).all()

    @staticmethod
    def relation_counts(customer_id, tenant_id, branch_id=None):
        """Count sales/payments/receipts tied to a customer (for delete guards)."""
        from models import Payment, Sale
        from models.receipt import Receipt

        sales_query = Sale.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        payments_query = Payment.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        receipts_query = Receipt.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        if branch_id is not None:
            sales_query = sales_query.filter(Sale.branch_id == branch_id)
            payments_query = payments_query.filter(Payment.branch_id == branch_id)
            receipts_query = receipts_query.filter(Receipt.branch_id == branch_id)
        return sales_query.count(), payments_query.count(), receipts_query.count()

    @staticmethod
    def attach_branch_labels(customers):
        """Annotate customers with branch labels aggregated from related transactions."""
        if not customers:
            return

        from models import Branch, Payment, Sale
        from models.receipt import Receipt

        customer_ids = [c.id for c in customers]
        branch_map: dict[Any, set[int]] = {cid: set() for cid in customer_ids}

        sale_rows = (
            db.session.query(Sale.customer_id, Sale.branch_id)
            .filter(
                Sale.customer_id.in_(customer_ids),
                Sale.branch_id.isnot(None),
            )
            .all()
        )
        payment_rows = (
            db.session.query(Payment.customer_id, Payment.branch_id)
            .filter(
                Payment.customer_id.in_(customer_ids),
                Payment.branch_id.isnot(None),
            )
            .all()
        )
        receipt_rows = (
            db.session.query(Receipt.customer_id, Receipt.branch_id)
            .filter(
                Receipt.customer_id.in_(customer_ids),
                Receipt.branch_id.isnot(None),
            )
            .all()
        )

        branch_ids = set()
        for cid, bid in sale_rows + payment_rows + receipt_rows:
            if cid in branch_map and bid:
                branch_map[cid].add(bid)
                branch_ids.add(bid)

        branches = Branch.query.filter(Branch.id.in_(branch_ids)).all() if branch_ids else []
        branch_labels = {b.id: (f"{b.name} ({b.code})" if getattr(b, "code", None) else b.name) for b in branches}

        for customer in customers:
            labels = [branch_labels.get(bid, str(bid)) for bid in sorted(branch_map.get(customer.id, set()))]
            customer.branch_labels = labels

    @staticmethod
    def branch_balance_map(customers, branch_id):
        """Per-customer branch-scoped balance map: receipts - sales - outgoing payments."""
        from decimal import Decimal

        from models import Payment, Sale
        from models.receipt import Receipt

        customer_ids = [c.id for c in customers]
        sales_rows = (
            db.session.query(
                Sale.customer_id,
                db.func.coalesce(db.func.sum(Sale.amount_aed), 0).label("sales_total"),
            )
            .filter(
                Sale.status == "confirmed",
                Sale.branch_id == branch_id,
                Sale.customer_id.in_(customer_ids),
            )
            .group_by(Sale.customer_id)
            .all()
        )
        receipts_rows = (
            db.session.query(
                Receipt.customer_id,
                db.func.coalesce(db.func.sum(Receipt.amount_aed), 0).label("receipts_total"),
            )
            .filter(
                Receipt.branch_id == branch_id,
                Receipt.customer_id.in_(customer_ids),
            )
            .group_by(Receipt.customer_id)
            .all()
        )
        outgoing_rows = (
            db.session.query(
                Payment.customer_id,
                db.func.coalesce(db.func.sum(Payment.amount_aed), 0).label("outgoing_total"),
            )
            .filter(
                Payment.direction == "outgoing",
                Payment.branch_id == branch_id,
                Payment.customer_id.in_(customer_ids),
            )
            .group_by(Payment.customer_id)
            .all()
        )

        sales_map = {cid: Decimal(str(total or 0)) for cid, total in sales_rows}
        receipts_map = {cid: Decimal(str(total or 0)) for cid, total in receipts_rows}
        outgoing_map = {cid: Decimal(str(total or 0)) for cid, total in outgoing_rows}

        balance_map = {}
        for cid in customer_ids:
            balance_map[cid] = (
                receipts_map.get(cid, Decimal("0"))
                - sales_map.get(cid, Decimal("0"))
                - outgoing_map.get(cid, Decimal("0"))
            )
        return balance_map

    @staticmethod
    def statement_records(customer_id, tenant_id, date_from, date_to, branch_id=None):
        """Ordered sales/payments/receipts/approved-returns lists for a statement period."""
        from sqlalchemy import func

        from models import Payment, ProductReturn, Sale
        from models.receipt import Receipt

        sales_q = Sale.query.filter_by(customer_id=customer_id, status="confirmed", tenant_id=tenant_id)
        payments_q = Payment.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        receipts_q = Receipt.query.filter_by(customer_id=customer_id, tenant_id=tenant_id)
        returns_q = ProductReturn.query.filter_by(customer_id=customer_id, status="approved", tenant_id=tenant_id)
        if branch_id is not None:
            sales_q = sales_q.filter(Sale.branch_id == branch_id)
            payments_q = payments_q.filter(Payment.branch_id == branch_id)
            receipts_q = receipts_q.filter(Receipt.branch_id == branch_id)
            returns_q = returns_q.filter(ProductReturn.branch_id == branch_id)

        if date_from:
            sales_q = sales_q.filter(func.date(Sale.sale_date) >= date_from)
            payments_q = payments_q.filter(func.date(Payment.payment_date) >= date_from)
            receipts_q = receipts_q.filter(func.date(Receipt.receipt_date) >= date_from)
            returns_q = returns_q.filter(func.date(ProductReturn.return_date) >= date_from)
        if date_to:
            sales_q = sales_q.filter(func.date(Sale.sale_date) <= date_to)
            payments_q = payments_q.filter(func.date(Payment.payment_date) <= date_to)
            receipts_q = receipts_q.filter(func.date(Receipt.receipt_date) <= date_to)
            returns_q = returns_q.filter(func.date(ProductReturn.return_date) <= date_to)

        return {
            "sales": sales_q.order_by(Sale.sale_date).all(),
            "payments": payments_q.order_by(Payment.payment_date).all(),
            "receipts": receipts_q.order_by(Receipt.receipt_date).all(),
            "returns": returns_q.order_by(ProductReturn.return_date).all(),
        }

    @staticmethod
    def statement_opening_balance(customer_id, tenant_id, date_from):
        """Opening balance before *date_from*: (payments+receipts+returns) - confirmed sales."""
        from sqlalchemy import func

        from models import Payment, ProductReturn, Sale
        from models.receipt import Receipt

        pre_sales = float(
            Sale.query.filter(
                Sale.customer_id == customer_id,
                Sale.status == "confirmed",
                Sale.tenant_id == tenant_id,
                func.date(Sale.sale_date) < date_from,
            )
            .with_entities(func.coalesce(func.sum(Sale.amount_aed), 0))
            .scalar()
            or 0
        )
        pre_pay = sum(
            (float(p.amount_aed or 0) if p.direction == "incoming" else -float(p.amount_aed or 0))
            for p in Payment.query.filter(
                Payment.customer_id == customer_id,
                Payment.tenant_id == tenant_id,
                func.date(Payment.payment_date) < date_from,
            ).all()
            if p.payment_confirmed or (p.payment_method == "cheque" and not p.rejection_reason)
        )
        pre_receipt = sum(
            float(r.amount_aed or 0)
            for r in Receipt.query.filter(
                Receipt.customer_id == customer_id,
                Receipt.tenant_id == tenant_id,
                func.date(Receipt.receipt_date) < date_from,
            ).all()
            if r.payment_confirmed or (r.payment_method == "cheque" and not r.rejection_reason)
        )
        pre_return = float(
            ProductReturn.query.filter(
                ProductReturn.customer_id == customer_id,
                ProductReturn.status == "approved",
                ProductReturn.tenant_id == tenant_id,
                func.date(ProductReturn.return_date) < date_from,
            )
            .with_entities(func.coalesce(func.sum(ProductReturn.amount_aed), 0))
            .scalar()
            or 0
        )
        return (pre_pay + pre_receipt + pre_return) - pre_sales
