"""Quotation service tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models import Customer
from services.quotation_service import QuotationService


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
