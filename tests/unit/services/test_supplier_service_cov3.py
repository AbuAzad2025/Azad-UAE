"""Coverage boost for services/supplier_service.py.

Targets: branch-scoped totals/labels/counts/ledger/print queries with data,
scoped_suppliers_query union hit, supplier_scoped_totals incoming-vs-outgoing,
preperiod_opening_balance cheque/confirmed logic + branch filter + returns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _purchase(db_session, tenant_id, supplier_id, branch_id=None, status="confirmed", amount="100", user_id=1):
    from models import Purchase

    p = Purchase(
        tenant_id=tenant_id,
        purchase_number=_uniq("PUR"),
        supplier_id=supplier_id,
        supplier_name="S",
        purchase_date=datetime.now(UTC),
        status=status,
        total_amount=Decimal(amount),
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        subtotal=Decimal(amount),
        currency="AED",
        user_id=user_id,
    )
    if branch_id is not None:
        p.branch_id = branch_id
    db_session.add(p)
    db_session.flush()
    return p


def _payment(
    db_session, tenant_id, supplier_id, branch_id=None, amount="10", direction="outgoing", confirmed=True, method="cash"
):
    from models import Payment

    p = Payment(
        tenant_id=tenant_id,
        payment_number=_uniq("SPAY"),
        payment_type="supplier_payment",
        direction=direction,
        supplier_id=supplier_id,
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


class TestScopedQueryUnionHit:
    def test_branch_query_includes_supplier_with_purchase(
        self, db_session, sample_tenant, sample_supplier, sample_branch
    ):
        from services.supplier_service import SupplierService

        _purchase(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id)
        db_session.commit()
        q = SupplierService.scoped_suppliers_query(branch_id=sample_branch.id)
        ids = [s.id for s in q.all()]
        assert sample_supplier.id in ids
        assert SupplierService.supplier_in_branch_scope(sample_supplier.id, sample_branch.id) is True

    def test_branch_query_includes_supplier_with_payment(self, db_session, sample_tenant, sample_branch):
        from services.supplier_service import SupplierService
        from services.supplier_service import SupplierService as SS

        s = SS.create_supplier(name=_uniq("S"), tenant_id=sample_tenant.id)
        db_session.flush()
        _payment(db_session, sample_tenant.id, s.id, branch_id=sample_branch.id)
        db_session.commit()
        q = SupplierService.scoped_suppliers_query(branch_id=sample_branch.id)
        assert s.id in [x.id for x in q.all()]


class TestTotalsWithDataAndBranch:
    def test_totals_sum_confirmed_only_and_outgoing_only(
        self, db_session, sample_tenant, sample_supplier, sample_branch
    ):
        from services.supplier_service import SupplierService

        _purchase(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            branch_id=sample_branch.id,
            status="confirmed",
            amount="100",
        )
        _purchase(
            db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id, status="draft", amount="999"
        )
        _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            branch_id=sample_branch.id,
            amount="40",
            direction="outgoing",
        )
        _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            branch_id=sample_branch.id,
            amount="500",
            direction="incoming",
        )
        db_session.commit()
        purchases, total_pur, total_paid = SupplierService.supplier_scoped_totals(
            sample_supplier.id, tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert total_pur == Decimal("100")
        assert total_paid == Decimal("40")
        assert len(purchases) == 1

    def test_totals_without_branch(self, db_session, sample_tenant, sample_supplier):
        from services.supplier_service import SupplierService

        _purchase(db_session, sample_tenant.id, sample_supplier.id, amount="50")
        db_session.commit()
        _, total_pur, _ = SupplierService.supplier_scoped_totals(sample_supplier.id, tenant_id=sample_tenant.id)
        assert total_pur == Decimal("50")


class TestLabelsCountsQueriesBranch:
    def test_branch_labels_with_code_and_fallback(self, db_session, sample_tenant, sample_supplier, sample_branch):
        from services.supplier_service import SupplierService

        sample_branch.code = "SB1"
        _purchase(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id)
        _payment(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id)
        db_session.commit()
        labels = SupplierService.supplier_branch_labels([sample_supplier.id])
        assert f"{sample_branch.name} ({sample_branch.code})" in labels[sample_supplier.id]
        sample_branch.code = ""
        db_session.flush()
        db_session.commit()
        labels2 = SupplierService.supplier_branch_labels([sample_supplier.id])
        assert sample_branch.name in labels2[sample_supplier.id]

    def test_linked_counts_branch(self, db_session, sample_tenant, sample_supplier, sample_branch):
        from services.supplier_service import SupplierService

        _purchase(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id)
        _payment(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id)
        db_session.commit()
        counts = SupplierService.supplier_linked_counts(
            sample_supplier.id, tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert counts["purchases"] >= 1
        assert counts["payments"] >= 1

    def test_ledger_and_print_queries_branch(self, db_session, sample_tenant, sample_supplier, sample_branch):
        from services.supplier_service import SupplierService

        pq, rq = SupplierService.statement_ledger_queries(
            sample_supplier.id, tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert pq is not None and rq is not None
        p_q, pay_q, r_q = SupplierService.print_statement_queries(
            sample_supplier.id, tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert p_q is not None and pay_q is not None and r_q is not None


class TestPreperiodOpeningBalance:
    def test_confirmed_cheque_and_direction_math(self, db_session, sample_tenant, sample_supplier):
        from services.supplier_service import SupplierService

        _purchase(db_session, sample_tenant.id, sample_supplier.id, amount="200")
        _payment(db_session, sample_tenant.id, sample_supplier.id, amount="50", direction="outgoing", confirmed=True)
        _payment(db_session, sample_tenant.id, sample_supplier.id, amount="30", direction="incoming", confirmed=True)
        # pending cheque without rejection counts
        _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            amount="20",
            direction="outgoing",
            confirmed=False,
            method="cheque",
        )
        # pending cash ignored
        _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            amount="400",
            direction="outgoing",
            confirmed=False,
            method="cash",
        )
        # rejected cheque ignored
        bad = _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            amount="60",
            direction="outgoing",
            confirmed=False,
            method="cheque",
        )
        bad.rejection_reason = "bounced"
        db_session.flush()
        db_session.commit()
        bal = SupplierService.preperiod_opening_balance(sample_supplier.id, "2100-01-01", tenant_id=sample_tenant.id)
        # 200 - 50 + 30 - 20 = 160
        assert bal == 160.0

    def test_branch_filter_and_returns(self, db_session, sample_tenant, sample_supplier, sample_branch):
        from models import PurchaseReturn
        from services.supplier_service import SupplierService

        pur = _purchase(db_session, sample_tenant.id, sample_supplier.id, branch_id=sample_branch.id, amount="100")
        _payment(
            db_session,
            sample_tenant.id,
            sample_supplier.id,
            branch_id=sample_branch.id,
            amount="10",
            direction="outgoing",
        )
        ret = PurchaseReturn(
            tenant_id=sample_tenant.id,
            purchase_id=pur.id,
            supplier_id=sample_supplier.id,
            branch_id=sample_branch.id,
            return_number=_uniq("RET"),
            amount_aed=Decimal("15"),
            total_amount=Decimal("15"),
            subtotal=Decimal("15"),
            return_date=datetime.now(UTC),
        )
        db_session.add(ret)
        db_session.flush()
        db_session.commit()
        bal = SupplierService.preperiod_opening_balance(
            sample_supplier.id, "2100-01-01", tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert bal == 100.0 - 10.0 - 15.0
