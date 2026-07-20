"""Tax service — strategy dispatch, sale/purchase tax, VAT return."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _strategy(country="AE"):
    s = MagicMock(country_code=country)
    s.calculate_tax.return_value = {
        "tax_amount": Decimal("5"),
        "net_amount": Decimal("95"),
        "total_amount": Decimal("100"),
        "rate_applied": Decimal("5"),
    }
    s.format_tax_return.return_value = {
        "output_vat": Decimal("100"),
        "input_vat": Decimal("40"),
        "net_vat": Decimal("60"),
    }
    return s


class TestTaxService:
    """TaxService — country strategy and GL-backed VAT return."""

    def test_calculate_sale_tax_uses_tenant_country(self, mocker):
        tenant = MagicMock(vat_country="ae")
        mocker.patch("models.Tenant.query").get.return_value = tenant
        mocker.patch("utils.localization.get_strategy", return_value=_strategy("AE"))
        sale = MagicMock(amount_aed=100, tax_rate=5)

        from services.tax_service import TaxService

        result = TaxService.calculate_sale_tax(sale, tenant_id=1)
        assert result["strategy"] == "AE"
        assert result["tax_amount"] == Decimal("5")

    def test_calculate_purchase_tax(self, mocker):
        mocker.patch("services.tax_service.TaxService._get_strategy", return_value=_strategy())
        purchase = MagicMock(amount_aed=200, tax_rate=5)

        from services.tax_service import TaxService

        result = TaxService.calculate_purchase_tax(purchase, tenant_id=2)
        assert result["total_amount"] == Decimal("100")

    def test_get_strategy_defaults_ae_without_tenant(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("models.Tenant.query").get.return_value = None
        strat = _strategy("AE")
        mocker.patch("utils.localization.get_strategy", return_value=strat)

        from services.tax_service import TaxService

        assert TaxService._get_strategy().country_code == "AE"

    def test_get_vat_return_gl_fallback_on_error(self, mocker):
        mocker.patch("services.tax_service.TaxService._get_strategy", return_value=_strategy())
        mocker.patch(
            "services.gl_service.GLService.get_vat_report",
            side_effect=RuntimeError("gl"),
        )
        from services.tax_service import TaxService

        result = TaxService.get_vat_return("2025-01-01", "2025-01-31", tenant_id=1)
        assert result["source"] == "gl"
        assert result["net_vat"] == Decimal("60")

    def test_get_vat_return_uses_gl_amounts(self, mocker):
        mocker.patch("services.tax_service.TaxService._get_strategy", return_value=_strategy())
        mocker.patch(
            "services.gl_service.GLService.get_vat_report",
            return_value={"vat_output": 150, "vat_input": 50},
        )
        from services.tax_service import TaxService

        result = TaxService.get_vat_return("2025-01-01", "2025-01-31", tenant_id=1)
        assert result["source"] == "gl"
