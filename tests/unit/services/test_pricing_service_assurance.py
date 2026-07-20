"""Pricing service — tiers, margins, customer types, currency formatting."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _tier(code, min_qty, price):
    t = MagicMock()
    t.tier_code = code
    t.min_quantity = Decimal(str(min_qty))
    t.price = Decimal(str(price))
    return t


def _mock_tier_query(mocker, tier):
    from models.product_price_tier import ProductPriceTier

    mock_q = MagicMock()
    mock_q.filter_by.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = tier
    mocker.patch.object(
        ProductPriceTier,
        "query",
        new_callable=mocker.PropertyMock,
        return_value=mock_q,
    )
    return mock_q


class TestTieredPricing:
    """get_price — quantity tier selection."""

    def test_tier_price_wins_over_base(self, mocker):
        product = MagicMock(id=1, regular_price=Decimal("100"))
        _mock_tier_query(mocker, _tier("wholesale", 10, "85"))

        from services.pricing_service import PricingService

        price = PricingService.get_price(product, qty=12)
        assert price == Decimal("85")

    def test_partner_discount_when_no_tier(self, mocker):
        product = MagicMock(
            id=2,
            regular_price=Decimal("200"),
            partner_price=Decimal("10"),
            merchant_price=None,
        )
        _mock_tier_query(mocker, None)

        from services.pricing_service import PricingService

        price = PricingService.get_price(product, customer_type="partner", qty=1)
        assert price == Decimal("180")

    def test_merchant_discount_applied(self, mocker):
        product = MagicMock(
            id=3,
            regular_price=Decimal("100"),
            partner_price=None,
            merchant_price=Decimal("25"),
        )
        _mock_tier_query(mocker, None)

        from services.pricing_service import PricingService

        price = PricingService.get_price(product, customer_type="merchant", qty=1)
        assert price == Decimal("75")

    def test_regular_customer_uses_regular_price(self, mocker):
        product = MagicMock(id=4, regular_price=Decimal("50"), partner_price=10, merchant_price=10)
        _mock_tier_query(mocker, None)

        from services.pricing_service import PricingService

        assert PricingService.get_price(product, customer_type="regular", qty=1) == Decimal("50")


class TestSaleLinePricing:
    """get_price_for_sale_line — discount + commission bundle."""

    def test_returns_tier_code_and_commission(self, mocker):
        product = MagicMock(id=5, regular_price=Decimal("100"), partner_price=Decimal("5"))
        tier = _tier("bulk", 5, "90")
        _mock_tier_query(mocker, tier)

        customer = MagicMock(customer_type="partner")
        rep = MagicMock(commission_rate=Decimal("3"))

        from services.pricing_service import PricingService

        result = PricingService.get_price_for_sale_line(product, qty=10, customer=customer, sales_rep=rep)
        assert result["unit_price"] == Decimal("90")
        assert result["tier_code"] == "bulk"
        assert result["discount_applied"] == Decimal("5")
        assert result["commission_rate"] == Decimal("3")

    def test_no_customer_defaults_regular(self, mocker):
        product = MagicMock(id=6, regular_price=Decimal("40"))
        _mock_tier_query(mocker, None)

        from services.pricing_service import PricingService

        result = PricingService.get_price_for_sale_line(product, qty=1, customer=None)
        assert result["unit_price"] == Decimal("40")
        assert result["tier_code"] is None
        assert result["discount_applied"] == Decimal("0")


class TestFormatPrice:
    """format_price — multi-currency display stability."""

    def test_delegates_to_currency_formatter(self, mocker):
        import utils.currency_utils as cu

        mocker.patch.object(cu, "format_currency_value", return_value="AED 1,234.50", create=True)

        from services.pricing_service import PricingService

        out = PricingService.format_price("1234.5", currency="AED")
        assert out == "AED 1,234.50"
        cu.format_currency_value.assert_called_once_with(Decimal("1234.5"), "AED")

    def test_decimal_string_conversion_stable(self, mocker):
        import utils.currency_utils as cu

        mocker.patch.object(
            cu,
            "format_currency_value",
            side_effect=lambda p, c: f"{c}:{p}",
            create=True,
        )

        from services.pricing_service import PricingService

        assert PricingService.format_price(99.99, currency="USD") == "USD:99.99"
