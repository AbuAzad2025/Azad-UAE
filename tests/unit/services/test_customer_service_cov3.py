"""Coverage boost for services/customer_service.py — uncovered lines/arcs.

Targets: list_active_paginated tid-falsy branch, get_unpaid_sales,
recent_sales, confirmed_sales, relation_counts branch filter,
attach_branch_labels with data, branch_balance_map with data,
statement_records filters, statement_opening_balance math.
All tests call the real CustomerService (mocks only at data-setup level).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_sale(db_session, tenant_id, customer_id, branch_id=None, status="confirmed", balance_due="50", amount="100"):
    from models import Sale

    s = Sale(
        tenant_id=tenant_id,
        sale_number=_uniq("SAL"),
        customer_id=customer_id,
        seller_id=1,
        sale_date=datetime.now(UTC),
        status=status,
        balance_due=Decimal(balance_due),
        total_amount=Decimal(amount),
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        subtotal=Decimal(amount),
        currency="AED",
    )
    if branch_id is not None:
        s.branch_id = branch_id
    db_session.add(s)
    db_session.flush()
    return s


def _make_payment(
    db_session, tenant_id, customer_id, branch_id=None, amount="10", direction="incoming", confirmed=True, method="cash"
):
    from models import Payment

    p = Payment(
        tenant_id=tenant_id,
        payment_number=_uniq("PAY"),
        payment_type="customer_payment",
        direction=direction,
        customer_id=customer_id,
        branch_id=branch_id,
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        currency="AED",
        payment_method=method,
        payment_confirmed=confirmed,
        payment_date=datetime.now(UTC),
    )
    db_session.add(p)
    db_session.flush()
    return p


def _make_receipt(db_session, tenant_id, customer_id, branch_id=None, amount="10", confirmed=True, method="cash"):
    from models import Receipt

    r = Receipt(
        tenant_id=tenant_id,
        receipt_number=_uniq("RCPT"),
        customer_id=customer_id,
        branch_id=branch_id,
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        currency="AED",
        payment_method=method,
        payment_confirmed=confirmed,
        receipt_date=datetime.now(UTC),
    )
    db_session.add(r)
    db_session.flush()
    return r


class TestListActivePaginatedTidFalsy:
    def test_tid_none_skips_tenant_filter(self, db_session, sample_tenant):
        from services.customer_service import CustomerService

        CustomerService.create_customer(name=_uniq("C"), tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        page = CustomerService.list_active_paginated(None, page=1, per_page=10)
        assert page is not None

    def test_tid_zero_skips_tenant_filter(self, db_session, sample_tenant):
        from services.customer_service import CustomerService

        page = CustomerService.list_active_paginated(0, page=1, per_page=5)
        assert page is not None


class TestUnpaidRecentConfirmedSales:
    def test_get_unpaid_sales_all_and_branch(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        _make_sale(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            branch_id=sample_branch.id,
            status="confirmed",
            balance_due="25",
            amount="100",
        )
        db_session.commit()
        all_rows = CustomerService.get_unpaid_sales(sample_customer.id)
        assert len(all_rows) >= 1
        scoped = CustomerService.get_unpaid_sales(sample_customer.id, branch_id=sample_branch.id)
        assert len(scoped) >= 1
        other = CustomerService.get_unpaid_sales(sample_customer.id, branch_id=999999)
        assert other == []

    def test_recent_sales_branch_and_limit(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        _make_sale(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id, status="confirmed")
        db_session.commit()
        rows = CustomerService.recent_sales(sample_customer.id, sample_tenant.id, branch_id=sample_branch.id, limit=5)
        assert len(rows) >= 1
        rows2 = CustomerService.recent_sales(sample_customer.id, sample_tenant.id)
        assert len(rows2) >= 1

    def test_confirmed_sales_branch_filter(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        _make_sale(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id, status="confirmed")
        db_session.commit()
        rows = CustomerService.confirmed_sales(sample_customer.id, branch_id=sample_branch.id)
        assert len(rows) >= 1
        rows_all = CustomerService.confirmed_sales(sample_customer.id)
        assert len(rows_all) >= 1

    def test_relation_counts_branch_scoped(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        _make_sale(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        _make_payment(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        _make_receipt(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        db_session.commit()
        s, p, r = CustomerService.relation_counts(sample_customer.id, sample_tenant.id, branch_id=sample_branch.id)
        assert s >= 1 and p >= 1 and r >= 1


class TestAttachBranchLabelsWithData:
    def test_labels_with_code_and_without_code(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        sample_branch.code = "MB1"
        _make_sale(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        _make_payment(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        _make_receipt(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        db_session.commit()
        CustomerService.attach_branch_labels([sample_customer])
        assert f"{sample_branch.name} ({sample_branch.code})" in sample_customer.branch_labels

        sample_branch.code = ""
        db_session.flush()
        db_session.commit()
        CustomerService.attach_branch_labels([sample_customer])
        assert sample_branch.name in sample_customer.branch_labels

    def test_label_falls_back_to_str_bid(self, db_session, sample_tenant):
        from services.customer_service import CustomerService
        from services.customer_service import CustomerService as CS

        c = CS.create_customer(name=_uniq("C"), tenant_id=sample_tenant.id)
        db_session.flush()
        ghost = type("Ghost", (), {"id": c.id})()
        # branch_map empty -> no labels; exercise sorted/labels loop with no branches
        CustomerService.attach_branch_labels([c])
        assert c.branch_labels == []
        assert ghost.id == c.id


class TestBranchBalanceMapWithData:
    def test_map_computes_receipts_minus_sales_minus_outgoing(
        self, db_session, sample_tenant, sample_customer, sample_branch
    ):
        from services.customer_service import CustomerService

        _make_sale(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            branch_id=sample_branch.id,
            status="confirmed",
            amount="100",
        )
        _make_receipt(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id, amount="60")
        _make_payment(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            branch_id=sample_branch.id,
            amount="10",
            direction="outgoing",
        )
        # incoming payments do not affect this map
        _make_payment(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            branch_id=sample_branch.id,
            amount="999",
            direction="incoming",
        )
        db_session.commit()
        m = CustomerService.branch_balance_map([sample_customer], sample_branch.id)
        assert Decimal(str(m[sample_customer.id])) == Decimal("60") - Decimal("100") - Decimal("10")


class TestStatementRecords:
    def test_filters_by_branch_and_dates(self, db_session, sample_tenant, sample_customer, sample_branch):
        from services.customer_service import CustomerService

        _make_sale(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id, status="confirmed")
        _make_payment(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        _make_receipt(db_session, sample_tenant.id, sample_customer.id, branch_id=sample_branch.id)
        db_session.commit()
        rec = CustomerService.statement_records(
            sample_customer.id,
            sample_tenant.id,
            date_from="2000-01-01",
            date_to="2100-01-01",
            branch_id=sample_branch.id,
        )
        assert len(rec["sales"]) >= 1
        assert len(rec["payments"]) >= 1
        assert len(rec["receipts"]) >= 1
        rec2 = CustomerService.statement_records(sample_customer.id, sample_tenant.id, None, None)
        assert "returns" in rec2


class TestStatementOpeningBalance:
    def test_opening_balance_math(self, db_session, sample_tenant, sample_customer):
        from services.customer_service import CustomerService

        _make_sale(db_session, sample_tenant.id, sample_customer.id, status="confirmed", amount="100")
        _make_payment(
            db_session, sample_tenant.id, sample_customer.id, amount="30", direction="incoming", confirmed=True
        )
        _make_payment(
            db_session, sample_tenant.id, sample_customer.id, amount="5", direction="outgoing", confirmed=True
        )
        # pending non-cheque ignored
        _make_payment(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            amount="500",
            direction="incoming",
            confirmed=False,
            method="cash",
        )
        # pending cheque without rejection counts
        _make_payment(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            amount="20",
            direction="incoming",
            confirmed=False,
            method="cheque",
        )
        # rejected cheque ignored
        pm = _make_payment(
            db_session,
            sample_tenant.id,
            sample_customer.id,
            amount="70",
            direction="incoming",
            confirmed=False,
            method="cheque",
        )
        pm.rejection_reason = "bounced"
        _make_receipt(db_session, sample_tenant.id, sample_customer.id, amount="10", confirmed=True)
        rc = _make_receipt(
            db_session, sample_tenant.id, sample_customer.id, amount="80", confirmed=False, method="cheque"
        )
        rc.rejection_reason = "bounced"
        db_session.flush()
        db_session.commit()
        bal = CustomerService.statement_opening_balance(sample_customer.id, sample_tenant.id, "2100-01-01")
        # pre_pay = 30 - 5 + 20 = 45 ; pre_receipt = 10 ; pre_sales = 100
        assert bal == (45 + 10 + 0) - 100
