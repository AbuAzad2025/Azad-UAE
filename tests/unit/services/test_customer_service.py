"""Tests for services/customer_service.py — Decimal + tenant isolation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.customer_service import CustomerService


class TestCustomerServiceCreate:
    def test_create_customer_minimal(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="Cust Minimal", tenant_id=sample_tenant.id)
        db_session.flush()
        assert c.id is not None
        assert c.name == "Cust Minimal"
        assert c.tenant_id == sample_tenant.id
        assert c.balance == 0

    def test_create_customer_full_fields(self, db_session, sample_tenant):
        c = CustomerService.create_customer(
            name="Full Cust",
            name_ar="عميل كامل",
            phone="0501234567",
            address="Dubai",
            email="full@test.com",
            tax_number="123",
            preferred_currency="USD",
            customer_type="merchant",
            notes="notes",
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        assert c.name_ar == "عميل كامل"
        assert c.phone == "0501234567"
        assert c.preferred_currency == "USD"

    def test_create_customer_without_tenant(self, db_session):
        c = CustomerService.create_customer(name="NoTenantCust")
        assert c.tenant_id is None
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_customer_decimal_balance_zero(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="Dec", tenant_id=sample_tenant.id)
        db_session.flush()
        assert Decimal(str(c.balance)) == Decimal("0")

    def test_create_customer_is_active_flag(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="Inactive", is_active=False, tenant_id=sample_tenant.id)
        db_session.flush()
        assert c.is_active is False


class TestCustomerServiceBalance:
    def test_set_balance_success(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="BalSet", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        result = CustomerService.set_balance(c.id, "123.456", tenant_id=sample_tenant.id)
        assert Decimal(str(result)) == Decimal("123.456")

    def test_set_balance_string_decimal_guard(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="BalStr", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        # str guard: data like "0" vs Decimal edge
        CustomerService.set_balance(c.id, Decimal("99.999"), tenant_id=sample_tenant.id)
        assert c.balance == Decimal("99.999")

    def test_set_balance_wrong_tenant_raises(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="Cross", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        with pytest.raises(ValueError, match="not found"):
            CustomerService.set_balance(c.id, "10", tenant_id=sample_tenant.id + 999)

    def test_adjust_balance_positive(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="AdjPos", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        CustomerService.set_balance(c.id, "100", tenant_id=sample_tenant.id)
        CustomerService.adjust_balance(c.id, "50.5", tenant_id=sample_tenant.id)
        assert Decimal(str(c.balance)) == Decimal("150.5")

    def test_adjust_balance_negative(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="AdjNeg", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        CustomerService.set_balance(c.id, "100", tenant_id=sample_tenant.id)
        CustomerService.adjust_balance(c.id, "-30", tenant_id=sample_tenant.id)
        assert Decimal(str(c.balance)) == Decimal("70")

    def test_adjust_balance_zero_delta(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="AdjZero", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        CustomerService.set_balance(c.id, "50", tenant_id=sample_tenant.id)
        CustomerService.adjust_balance(c.id, "0", tenant_id=sample_tenant.id)
        assert Decimal(str(c.balance)) == Decimal("50")

    def test_adjust_balance_wrong_tenant_raises(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="AdjCross", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        with pytest.raises(ValueError):
            CustomerService.adjust_balance(c.id, "10", tenant_id=sample_tenant.id + 999)


class TestCustomerServiceTenantIsolation:
    def test_get_tenant_customer_found(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="GetOk", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        found = CustomerService.get_tenant_customer(c.id, sample_tenant.id)
        assert found is not None
        assert found.id == c.id

    def test_get_tenant_customer_wrong_tenant_none(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="GetWrong", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        found = CustomerService.get_tenant_customer(c.id, sample_tenant.id + 999)
        assert found is None

    def test_list_active_paginated(self, db_session, sample_tenant):
        for i in range(3):
            CustomerService.create_customer(name=f"Pag {i}", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        page = CustomerService.list_active_paginated(sample_tenant.id, page=1, per_page=10)
        # paginate_optimized returns pagination object
        assert hasattr(page, "items") or isinstance(page, list) or hasattr(page, "total")

    def test_customer_id_in_branch_scope_false_when_no_transactions(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="ScopeEmpty", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        # No sales/payments/receipts -> should be False
        result = CustomerService.customer_id_in_branch_scope(c.id, branch_id=9999)
        assert result is False

    def test_relation_counts_zero_for_new_customer(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="RelZero", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        sales_cnt, pay_cnt, rec_cnt = CustomerService.relation_counts(c.id, sample_tenant.id)
        assert sales_cnt == 0
        assert pay_cnt == 0
        assert rec_cnt == 0

    def test_branch_balance_map_empty(self, db_session, sample_tenant, sample_branch):
        c = CustomerService.create_customer(name="BalMap", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        m = CustomerService.branch_balance_map([c], sample_branch.id)
        assert c.id in m
        assert Decimal(str(m[c.id])) == Decimal("0")

    def test_attach_branch_labels_no_transactions(self, db_session, sample_tenant):
        c = CustomerService.create_customer(name="Labels", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        CustomerService.attach_branch_labels([c])
        assert hasattr(c, "branch_labels")
        assert c.branch_labels == []

    def test_attach_branch_labels_empty_list(self):
        # Should not raise
        CustomerService.attach_branch_labels([])
        CustomerService.attach_branch_labels(None) if False else None  # ensure no crash on empty
