"""Cov4: store_pricing_service — currency coerce/resolve/rate/convert arcs."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from services.store_pricing_service import StorePricingService


def test_as_currency_code_branches():
    assert StorePricingService._as_currency_code(None) == ""
    assert StorePricingService._as_currency_code(123) == ""
    assert StorePricingService._as_currency_code(" usd ") == "USD"


def test_resolve_display_currency_priority():
    store = SimpleNamespace(display_currency=" eur ")
    assert StorePricingService.resolve_display_currency(store, SimpleNamespace(default_currency="AED")) == "EUR"
    store2 = SimpleNamespace(display_currency=None)
    assert StorePricingService.resolve_display_currency(store2, SimpleNamespace(default_currency="aed")) == "AED"
    store3 = SimpleNamespace()
    tenant3 = SimpleNamespace(get_base_currency=lambda: "usd")
    assert StorePricingService.resolve_display_currency(store3, tenant3) == "USD"


def test_base_currency_branches():
    assert StorePricingService._base_currency(None) == ""
    assert StorePricingService._base_currency(SimpleNamespace()) == ""
    t = SimpleNamespace(get_base_currency="GBP")
    assert StorePricingService._base_currency(t) == "GBP"
    t2 = SimpleNamespace(get_base_currency=lambda: None, base_currency="QAR")
    assert StorePricingService._base_currency(t2) == "QAR"


def test_resolve_rate_live_success():
    with patch(
        "services.currency_service.CurrencyService.get_exchange_rate_details",
        return_value={"rate": "3.67"},
    ):
        assert StorePricingService._resolve_rate("USD", "AED") == Decimal("3.67")


def test_resolve_rate_live_rates_dict():
    with patch(
        "services.currency_service.CurrencyService.get_exchange_rate_details",
        return_value={"rate": None, "rates": {"AED": "3.6725"}},
    ):
        assert StorePricingService._resolve_rate("USD", "AED") == Decimal("3.6725")


def test_resolve_rate_falls_to_stored():
    with patch(
        "services.currency_service.CurrencyService.get_exchange_rate_details",
        side_effect=RuntimeError("live down"),
    ), patch(
        "services.exchange_rate_service.ExchangeRateService.get_latest_rate",
        return_value=Decimal("3.5"),
    ):
        assert StorePricingService._resolve_rate("USD", "AED") == Decimal("3.5")


def test_resolve_rate_none_when_unresolvable():
    with patch(
        "services.currency_service.CurrencyService.get_exchange_rate_details",
        return_value={"rate": "0"},
    ), patch(
        "services.exchange_rate_service.ExchangeRateService.get_latest_rate",
        side_effect=RuntimeError("stored down"),
    ):
        assert StorePricingService._resolve_rate("USD", "XXX") is None


def test_convert_amount_same_and_norate_and_converted(sample_tenant):
    tenant = SimpleNamespace(get_base_currency=lambda: "AED", base_currency="AED")
    assert StorePricingService.convert_amount("10", tenant, "AED") == Decimal("10.00")
    assert StorePricingService.convert_amount("10", tenant, None) == Decimal("10.00")
    with patch.object(StorePricingService, "_resolve_rate", return_value=None):
        assert StorePricingService.convert_amount("10", tenant, "USD") == Decimal("10.00")
    with patch.object(StorePricingService, "_resolve_rate", return_value=Decimal("0.27")):
        assert StorePricingService.convert_amount("100", tenant, "USD") == Decimal("27.00")


def test_resolve_display_price(sample_product):
    tenant = SimpleNamespace(get_base_currency=lambda: "AED")
    with patch.object(StorePricingService, "convert_amount", return_value=Decimal("5.00")) as c:
        assert StorePricingService.resolve_display_price(sample_product, tenant, "USD") == Decimal("5.00")
        c.assert_called_once()
    store = SimpleNamespace(display_currency="USD")
    with patch.object(StorePricingService, "convert_amount", return_value=Decimal("7.00")):
        assert StorePricingService.resolve_display_price_for_store(sample_product, store, tenant) == Decimal("7.00")
