"""Cov5: pricing_service — partner/merchant without special price branch."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace


def test_partner_without_partner_price_no_discount(sample_product):
    from services.pricing_service import PricingService

    customer = SimpleNamespace(customer_type="partner")
    out = PricingService.get_price_for_sale_line(sample_product, 1, customer)
    assert out["discount_applied"] == Decimal("0")
    assert out["unit_price"] == sample_product.regular_price


def test_merchant_without_merchant_price_no_discount(sample_product):
    from services.pricing_service import PricingService

    customer = SimpleNamespace(customer_type="merchant")
    out = PricingService.get_price_for_sale_line(sample_product, 1, customer)
    assert out["discount_applied"] == Decimal("0")
