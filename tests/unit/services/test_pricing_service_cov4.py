"""Cov4: pricing_service — tier/partner/merchant/regular + formatter fallback arcs."""

from __future__ import annotations

from decimal import Decimal

from services.pricing_service import PricingService


def test_get_price_regular_no_tier(sample_product):
    assert PricingService.get_price(sample_product, "regular", 1) == sample_product.regular_price


def test_get_price_partner_discount(sample_product):
    sample_product.partner_price = Decimal("10")
    assert PricingService.get_price(sample_product, "partner", 1) == Decimal("90.000")


def test_get_price_merchant_discount(sample_product):
    sample_product.merchant_price = Decimal("20")
    assert PricingService.get_price(sample_product, "merchant", 1) == Decimal("80.000")


def test_get_price_partner_without_attr_falls_back(sample_product):
    sample_product.partner_price = None
    assert PricingService.get_price(sample_product, "partner", 1) == sample_product.regular_price


def test_get_price_with_tier(db_session, sample_product, sample_tenant):
    from models.product_price_tier import ProductPriceTier

    tier = ProductPriceTier(
        tenant_id=sample_tenant.id,
        product_id=sample_product.id,
        tier_code="BULK",
        min_quantity=Decimal("5"),
        price=Decimal("70.000"),
        is_active=True,
    )
    db_session.add(tier)
    db_session.flush()
    # qty below tier -> regular
    assert PricingService.get_price(sample_product, "regular", 1) == sample_product.regular_price
    # qty at tier -> tier price (tier branch)
    assert PricingService.get_price(sample_product, "partner", 10) == Decimal("70.000")


def test_get_price_for_sale_line_partner_with_rep(db_session, sample_product, sample_customer):
    from types import SimpleNamespace

    sample_customer.customer_type = "partner"
    sample_product.partner_price = Decimal("10")
    rep = SimpleNamespace(commission_rate=Decimal("5"))
    out = PricingService.get_price_for_sale_line(sample_product, 2, sample_customer, sales_rep=rep)
    assert out["discount_applied"] == Decimal("10")
    assert out["commission_rate"] == Decimal("5")
    assert out["tier_code"] is None
    assert out["unit_price"] == Decimal("90.000")


def test_get_price_for_sale_line_no_customer_no_rep(sample_product):
    out = PricingService.get_price_for_sale_line(sample_product, 1, None)
    assert out["discount_applied"] == Decimal("0")
    assert out["commission_rate"] == Decimal("0")


def test_get_price_for_sale_line_rep_without_rate(sample_product, sample_customer):
    from types import SimpleNamespace

    out = PricingService.get_price_for_sale_line(
        sample_product, 1, sample_customer, sales_rep=SimpleNamespace()
    )
    assert out["commission_rate"] == Decimal("0")


def test_format_price_with_formatter(monkeypatch):
    import utils.currency_utils as cu

    monkeypatch.setattr(cu, "format_currency_value", lambda a, c: f"FMT-{c}-{a}", raising=False)
    assert PricingService.format_price("12.5", "AED") == "FMT-AED-12.5"


def test_format_price_fallback(monkeypatch):
    import utils.currency_utils as cu

    monkeypatch.delattr(cu, "format_currency_value", raising=False)
    assert PricingService.format_price(Decimal("3.2"), "USD") == "USD:3.2"
