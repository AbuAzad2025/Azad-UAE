"""StorePricingService — unified storefront display pricing (P2, audit D1/D4)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _tenant(base="ILS", default="AED"):
    tenant = MagicMock()
    tenant.get_base_currency = MagicMock(return_value=base)
    tenant.default_currency = default
    tenant.base_currency = base
    return tenant


def _product(price="100"):
    return MagicMock(regular_price=Decimal(price))


def _store(display_currency=None):
    return MagicMock(display_currency=display_currency)


class TestDisplayCurrencyResolution:
    def test_explicit_store_currency_wins(self):
        from services.store_pricing_service import StorePricingService

        assert StorePricingService.resolve_display_currency(_store("USD"), _tenant()) == "USD"

    def test_falls_back_to_tenant_default(self):
        from services.store_pricing_service import StorePricingService

        assert StorePricingService.resolve_display_currency(_store(None), _tenant(default="JOD")) == "JOD"

    def test_falls_back_to_base(self):
        from services.store_pricing_service import StorePricingService

        assert StorePricingService.resolve_display_currency(_store(None), _tenant(base="ILS", default="")) == "ILS"


class TestDisplayPrice:
    def test_same_currency_no_conversion(self, app):
        from services.store_pricing_service import StorePricingService

        with app.app_context():
            price = StorePricingService.resolve_display_price(_product("99.9"), _tenant(base="AED"), "AED")
        assert price == Decimal("99.90")

    def test_converts_with_live_rate(self, app, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            return_value={"rate": Decimal("0.27")},
        )
        from services.store_pricing_service import StorePricingService

        with app.app_context():
            price = StorePricingService.resolve_display_price(_product("100"), _tenant(base="ILS"), "USD")
        assert price == Decimal("27.00")

    def test_falls_back_to_stored_rate_when_live_fails(self, app, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            side_effect=RuntimeError("offline"),
        )
        mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.get_latest_rate",
            return_value="0.25",
        )
        from services.store_pricing_service import StorePricingService

        with app.app_context():
            price = StorePricingService.resolve_display_price(_product("100"), _tenant(base="ILS"), "USD")
        assert price == Decimal("25.00")

    def test_no_silent_rate_one_when_unresolvable(self, app, mocker, caplog):
        """D4: when every rate source fails the price stays unconverted and a warning is logged."""
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            side_effect=RuntimeError("offline"),
        )
        mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.get_latest_rate",
            return_value=None,
        )
        from services.store_pricing_service import StorePricingService

        with caplog.at_level("WARNING", logger="services.store_pricing_service"):
            with app.app_context():
                price = StorePricingService.resolve_display_price(_product("100"), _tenant(base="ILS"), "USD")
        assert price == Decimal("100.00")
        assert any("NO rate" in rec.message for rec in caplog.records)

    def test_convert_amount_used_for_addons(self, app, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            return_value={"rate": Decimal("0.5")},
        )
        from services.store_pricing_service import StorePricingService

        with app.app_context():
            assert StorePricingService.convert_amount(Decimal("10"), _tenant(base="ILS"), "USD") == Decimal("5.00")


class TestCatalogConsistency:
    """D1: catalog display_price matches product-page dp() for the same product."""

    def test_catalog_price_matches_direct_resolution(self, app, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            return_value={"rate": Decimal("0.27")},
        )
        from services.store_pricing_service import StorePricingService

        tenant = _tenant(base="ILS", default="USD")
        product = _product("250")
        with app.app_context():
            via_catalog_signature = StorePricingService.resolve_display_price(product, tenant, "USD")
            via_product_page = StorePricingService.resolve_display_price_for_store(product, _store("USD"), tenant)
        assert via_catalog_signature == via_product_page == Decimal("67.50")
