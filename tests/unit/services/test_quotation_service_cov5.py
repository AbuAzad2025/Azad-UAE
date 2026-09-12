"""Cov5: quotation_service — already-converted guard branch."""

from __future__ import annotations

import pytest


def test_convert_already_converted_raises(db_session, sample_tenant, sample_user, sample_product):
    from models import Customer
    from services.quotation_service import QuotationService

    customer = Customer(tenant_id=sample_tenant.id, name="C-COV5", name_ar="C-COV5")
    db_session.add(customer)
    db_session.flush()
    q = QuotationService.create_quotation(
        {"customer_id": customer.id, "lines": [{"product_id": sample_product.id, "quantity": 1, "unit_price": 50}]},
        sample_user,
    )
    QuotationService.send_quotation(q)
    QuotationService.accept_quotation(q)
    q.sale_id = 424242
    with pytest.raises(ValueError, match="مسبق"):
        QuotationService.convert_to_sale(q, sample_user)
