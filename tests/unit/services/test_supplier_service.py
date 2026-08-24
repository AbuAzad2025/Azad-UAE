"""Tests for services/supplier_service.py — Decimal + tenant + branch scope."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.supplier_service import SupplierService


class TestSupplierServiceCreate:
    def test_create_supplier_minimal(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="Sup Minimal", tenant_id=sample_tenant.id)
        db_session.flush()
        assert s.id is not None
        assert s.name == "Sup Minimal"
        assert s.tenant_id == sample_tenant.id
        assert s.is_active is True

    def test_create_supplier_full(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(
            name="Full Sup",
            phone="0500000001",
            email="sup@test.com",
            address="Dubai",
            tax_number="T123",
            credit_limit=5000,
            payment_terms_days=45,
            preferred_currency="USD",
            rating=4,
            tags="vip,local",
            tenant_id=sample_tenant.id,
            created_by=1,
        )
        db_session.flush()
        assert s.phone == "0500000001"
        assert s.credit_limit == 5000
        assert s.payment_terms_days == 45
        assert s.rating == 4
        assert s.tags == "vip,local"

    def test_create_supplier_without_tenant(self, db_session):
        s = SupplierService.create_supplier(name="NoTenantSup")
        assert s.tenant_id is None
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_supplier_decimal_totals_zero(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="DecSup", tenant_id=sample_tenant.id)
        db_session.flush()
        assert Decimal(str(s.total_purchases_aed)) == Decimal("0")
        assert Decimal(str(s.total_paid_aed)) == Decimal("0")

    def test_create_supplier_is_verified_flag(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="VerifiedSup", is_verified=True, tenant_id=sample_tenant.id)
        db_session.flush()
        assert s.is_verified is True

    def test_create_supplier_unicode(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="مورد اختبار", tenant_id=sample_tenant.id)
        db_session.flush()
        assert s.name == "مورد اختبار"


class TestSupplierServiceBranchScope:
    def test_scoped_suppliers_query_no_branch(self, db_session, sample_tenant):
        SupplierService.create_supplier(name="ScopedNoBranch", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        q = SupplierService.scoped_suppliers_query(branch_id=None)
        # Should return tenant-scoped query, not filtered by branch
        assert q is not None

    def test_supplier_in_branch_scope_no_branch_always_true(self):
        assert SupplierService.supplier_in_branch_scope(1, branch_id=None) is True

    def test_supplier_in_branch_scope_false_when_no_transactions(self, db_session, sample_tenant, sample_branch):
        s = SupplierService.create_supplier(name="ScopeFalse", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        result = SupplierService.supplier_in_branch_scope(s.id, branch_id=sample_branch.id)
        assert result is False

    def test_supplier_scoped_totals_empty(self, db_session, sample_tenant, sample_branch):
        s = SupplierService.create_supplier(name="TotalsEmpty", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        purchases, total_pur, total_paid = SupplierService.supplier_scoped_totals(
            s.id, tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert purchases == []
        assert total_pur == 0
        assert total_paid == 0

    def test_supplier_branch_labels_empty(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="LabelEmpty", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        labels = SupplierService.supplier_branch_labels([s.id])
        assert s.id in labels
        assert labels[s.id] == []

    def test_supplier_linked_counts_zero(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="LinkZero", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        counts = SupplierService.supplier_linked_counts(s.id, tenant_id=sample_tenant.id)
        assert counts["purchases"] == 0
        assert counts["payments"] == 0

    def test_statement_ledger_queries_returns_queries(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="LedgerQ", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        pq, rq = SupplierService.statement_ledger_queries(s.id, tenant_id=sample_tenant.id)
        assert pq is not None
        assert rq is not None

    def test_print_statement_queries_returns_three(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="PrintQ", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        p_q, pay_q, r_q = SupplierService.print_statement_queries(s.id, tenant_id=sample_tenant.id)
        assert p_q is not None
        assert pay_q is not None
        assert r_q is not None

    def test_preperiod_opening_balance_no_date_returns_zero(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="OpeningNoDate", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        bal = SupplierService.preperiod_opening_balance(s.id, date_from=None, tenant_id=sample_tenant.id)
        assert bal == 0.0

    def test_preperiod_opening_balance_with_date_no_activity(self, db_session, sample_tenant):
        s = SupplierService.create_supplier(name="OpeningDate", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        bal = SupplierService.preperiod_opening_balance(s.id, date_from="2026-01-01", tenant_id=sample_tenant.id)
        assert bal == 0.0

    def test_scoped_suppliers_query_with_branch_returns_query(self, db_session, sample_tenant, sample_branch):
        SupplierService.create_supplier(name="ScopedBranch", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        q = SupplierService.scoped_suppliers_query(branch_id=sample_branch.id)
        # Should not raise, and filtered by branch union
        result = q.all()
        assert isinstance(result, list)
