"""Quotation service tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from models import Customer, Quotation
from services.quotation_service import QuotationService


def _q3(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _customer(db_session, sample_tenant, name):
    customer = Customer(tenant_id=sample_tenant.id, name=name, name_ar=name)
    db_session.add(customer)
    db_session.flush()
    return customer


class TestQuotationWorkflow:
    def test_create_quotation(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(
            tenant_id=sample_tenant.id,
            name="Test Customer",
            name_ar="عميل تجريبي",
        )
        db_session.add(customer)
        db_session.flush()

        data = {
            "customer_id": customer.id,
            "lines": [
                {
                    "product_id": sample_product.id,
                    "quantity": 5,
                    "unit_price": 100,
                    "discount_percent": 0,
                    "tax_rate": 5,
                },
            ],
        }
        q = QuotationService.create_quotation(data, sample_user)
        assert q.id is not None
        assert q.status == "draft"
        assert q.quotation_number.startswith("QT")
        assert q.total_amount == Decimal("525.000")

    def test_send_quotation(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C2", name_ar="C2")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q)
        assert q.status == "sent"

    def test_send_non_draft_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C3", name_ar="C3")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q)
        with pytest.raises(ValueError):
            QuotationService.send_quotation(q)

    def test_accept_quotation(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C4", name_ar="C4")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "lines": [{"product_id": sample_product.id, "quantity": 2, "unit_price": 100}],
            },
            sample_user,
        )
        QuotationService.send_quotation(q)
        QuotationService.accept_quotation(q)
        assert q.status == "accepted"

    def test_reject_quotation(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C5", name_ar="C5")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q)
        QuotationService.reject_quotation(q)
        assert q.status == "rejected"

    def test_convert_to_sale(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C6", name_ar="C6")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "lines": [{"product_id": sample_product.id, "quantity": 3, "unit_price": 200, "tax_rate": 5}],
            },
            sample_user,
        )
        QuotationService.send_quotation(q)
        QuotationService.accept_quotation(q)
        sale = QuotationService.convert_to_sale(q, sample_user)

        assert sale.id is not None
        assert sale.status == "draft"
        assert q.status == "converted_to_sale"
        assert q.sale_id == sale.id

    def test_convert_not_accepted_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C7", name_ar="C7")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        with pytest.raises(ValueError):
            QuotationService.convert_to_sale(q, sample_user)

    def test_duplicate_quotation(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C8", name_ar="C8")
        db_session.add(customer)
        db_session.flush()

        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 100}],
            },
            sample_user,
        )
        new_q = QuotationService.duplicate_quotation(q, sample_user)
        assert new_q.id != q.id
        assert new_q.status == "draft"
        assert new_q.total_amount == q.total_amount

    def test_list_quotations(self, db_session, sample_tenant, sample_user, sample_product):
        customer = Customer(tenant_id=sample_tenant.id, name="C9", name_ar="C9")
        db_session.add(customer)
        db_session.flush()

        QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        result = QuotationService.list_quotations(sample_tenant.id)
        assert len(result) >= 1


class TestQuotationUpdate:
    def test_update_scalar_fields(self, db_session, sample_tenant, sample_user, sample_product, sample_branch):
        customer = _customer(db_session, sample_tenant, "UPD-C1")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        updated = QuotationService.update_quotation(
            q,
            {
                "notes": "revised",
                "terms": "net 30",
                "currency": "USD",
                "exchange_rate": "3.6725",
                "base_currency": "AED",
                "prices_include_vat": True,
                "expiry_date": date(2027, 1, 31),
                "branch_id": None,
                "warehouse_id": None,
                "customer_id": str(customer.id),
            },
        )
        assert updated.notes == "revised"
        assert updated.terms == "net 30"
        assert updated.currency == "USD"
        assert updated.exchange_rate == Decimal("3.6725")
        assert updated.base_currency == "AED"
        assert updated.prices_include_vat is True
        assert updated.expiry_date == date(2027, 1, 31)
        assert updated.branch_id is None
        assert updated.warehouse_id is None
        assert updated.customer_id == customer.id

    def test_update_replaces_lines_and_recalculates_totals(self, db_session, sample_tenant, sample_user, sample_product):
        """Regression guard: replaced lines must drive recalculated totals (no stale ORM collection)."""
        customer = _customer(db_session, sample_tenant, "UPD-C2")
        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "lines": [{"product_id": sample_product.id, "quantity": 9, "unit_price": 999}],
            },
            sample_user,
        )
        old_line_ids = {line.id for line in q.lines}

        QuotationService.update_quotation(
            q,
            {
                "lines": [
                    {
                        "product_id": sample_product.id,
                        "quantity": "2",
                        "unit_price": "100",
                        "discount_percent": "10",
                        "tax_rate": "5",
                    }
                ]
            },
        )
        db_session.flush()
        db_session.expire(q)
        db_session.refresh(q)

        line_ids = {line.id for line in q.lines}
        assert line_ids.isdisjoint(old_line_ids)
        line = q.lines[0]
        # base 200, discount 20, taxable 180, tax 9 → line_total 189
        assert line.line_total == Decimal("189.000")
        assert q.subtotal == Decimal("200.000")
        assert q.discount_amount == Decimal("20.000")
        assert q.tax_amount == Decimal("9.000")
        assert q.total_amount == Decimal("189.000")
        assert q.amount_aed == Decimal("189.000")

    def test_update_non_draft_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "UPD-C3")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q)
        with pytest.raises(ValueError):
            QuotationService.update_quotation(q, {"notes": "late edit"})


class TestQuotationGuards:
    def test_accept_draft_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "GRD-C1")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        with pytest.raises(ValueError):
            QuotationService.accept_quotation(q)

    def test_accept_expired_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "GRD-C2")
        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "expiry_date": date.today() - timedelta(days=1),
                "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}],
            },
            sample_user,
        )
        QuotationService.send_quotation(q)
        assert q.is_expired is True
        with pytest.raises(ValueError):
            QuotationService.accept_quotation(q)

    def test_reject_draft_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "GRD-C3")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        with pytest.raises(ValueError):
            QuotationService.reject_quotation(q)

    def test_convert_twice_raises(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "GRD-C4")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q)
        QuotationService.accept_quotation(q)
        QuotationService.convert_to_sale(q, sample_user)
        with pytest.raises(ValueError):
            QuotationService.convert_to_sale(q, sample_user)

    def test_convert_copies_money_fields_as_decimal(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "GRD-C5")
        q = QuotationService.create_quotation(
            {
                "customer_id": customer.id,
                "currency": "USD",
                "exchange_rate": "3.5",
                "lines": [
                    {
                        "product_id": sample_product.id,
                        "quantity": "3",
                        "unit_price": "200",
                        "discount_percent": "10",
                        "tax_rate": "5",
                    }
                ],
            },
            sample_user,
        )
        QuotationService.send_quotation(q)
        QuotationService.accept_quotation(q)
        sale = QuotationService.convert_to_sale(q, sample_user)

        # base 600, disc 60, tax 27 → total 567 carried onto the sale
        assert sale.subtotal == Decimal("600.000")
        assert sale.discount_amount == Decimal("60.000")
        assert sale.tax_amount == Decimal("27.000")
        assert sale.total_amount == Decimal("567.000")
        assert sale.amount == Decimal("567.000")
        assert sale.amount_aed == Decimal("567.000")
        assert sale.currency == "USD"
        assert sale.exchange_rate == Decimal("3.5")
        assert len(sale.lines) == 1
        assert sale.lines[0].line_total == Decimal("567.000")


class TestQuotationLookup:
    def test_get_found_missing_and_cross_tenant(self, db_session, sample_tenant, sample_user, sample_product):
        customer = _customer(db_session, sample_tenant, "LK-C1")
        q = QuotationService.create_quotation(
            {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        assert QuotationService.get_quotation(q.id).id == q.id
        assert QuotationService.get_quotation(q.id, tenant_id=sample_tenant.id).id == q.id

        with pytest.raises(ValueError):
            QuotationService.get_quotation(99999999)

        from models import Tenant

        other_tenant = Tenant(
            name="Quotation Foreign Co",
            name_ar="أجنبي",
            slug=f"qtn-foreign-{db_session.query(Tenant).count()}",
            email="qtn-foreign@test.local",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other_tenant)
        db_session.flush()
        foreign_q = Quotation(
            tenant_id=other_tenant.id,
            quotation_number="QT-FOREIGN-1",
            customer_id=customer.id,
            created_by=sample_user.id,
            status="draft",
            total_amount=Decimal("10"),
        )
        db_session.add(foreign_q)
        db_session.flush()
        with pytest.raises(ValueError):
            QuotationService.get_quotation(foreign_q.id, tenant_id=sample_tenant.id)

    def test_list_filters_status_and_customer(self, db_session, sample_tenant, sample_user, sample_product):
        c1 = _customer(db_session, sample_tenant, "LST-C1")
        c2 = _customer(db_session, sample_tenant, "LST-C2")
        q1 = QuotationService.create_quotation(
            {"customer_id": c1.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
            sample_user,
        )
        QuotationService.send_quotation(q1)
        QuotationService.create_quotation(
            {"customer_id": c2.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 70}]},
            sample_user,
        )

        sent = QuotationService.list_quotations(sample_tenant.id, filters={"status": "sent"})
        assert [x.id for x in sent] == [q1.id]

        by_customer = QuotationService.list_quotations(sample_tenant.id, filters={"customer_id": str(c2.id)})
        assert all(x.customer_id == c2.id for x in by_customer)
        assert len(by_customer) >= 1
