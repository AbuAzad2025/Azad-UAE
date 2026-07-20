from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from utils.localization.null import NullStrategy
from utils.localization.palestine import PalestineStrategy


@pytest.fixture
def strategy():
    return PalestineStrategy()


class TestPalestineCalculateTax:
    def test_standard_vat(self, strategy):
        result = strategy.calculate_tax(Decimal("100"))
        assert result["tax_amount"] == Decimal("16.00")
        assert result["total_amount"] == Decimal("116.00")

    def test_zero_rated(self, strategy):
        result = strategy.calculate_tax(Decimal("80"), tax_rate=Decimal("0"))
        assert result["tax_amount"] == Decimal("0")
        assert result["total_amount"] == Decimal("80")


class TestPalestineTaxReturn:
    def test_format_tax_return(self, strategy):
        result = strategy.format_tax_return(
            Decimal("800"),
            Decimal("200"),
            "2025-03-01",
            "2025-03-31",
        )
        assert result["country"] == "PS"
        assert result["net_payable"] == Decimal("600")
        assert result["format"] == "pma_xml_v1"
        assert result["currency"] == "ILS"


class TestPalestineValidateTaxNumber:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("123456789", True),
            ("12345678901", True),
            ("12345", False),
            ("", False),
        ],
    )
    def test_vat_id_validation(self, strategy, value, expected):
        assert strategy.validate_tax_number(value) is expected


class TestPalestineCurrency:
    def test_same_currency_passthrough(self, strategy):
        assert strategy.convert_to_local_currency(Decimal("100"), "ILS") == Decimal("100.00")

    def test_missing_conversion_raises(self, strategy):
        with patch("utils.helpers.convert_currency", side_effect=KeyError("rate missing")):
            with pytest.raises(KeyError):
                strategy.convert_to_local_currency(Decimal("50"), "USD", "ILS")

    def test_unsupported_source_currency(self, strategy):
        with pytest.raises(ValueError, match="Unsupported source currency"):
            strategy.convert_to_local_currency(Decimal("10"), "EUR", "ILS")

    def test_convert_with_mocked_rate(self, strategy):
        with patch("utils.helpers.convert_currency", return_value=Decimal("3.65")):
            result = strategy.convert_to_local_currency(Decimal("100"), "USD", "ILS")
        assert result == Decimal("3.65")


class TestPalestineEInvoice:
    def test_generate_einvoice_uses_dynamic_rate(self, strategy):
        sale = MagicMock(id=10, total_aed=Decimal("116"), tax_rate=Decimal("16"))
        result = strategy.generate_einvoice(sale)
        assert result["format"] == "pma_mof_xml"
        assert "16" in result["xml_payload"]
        assert "TaxAmount" in result["xml_payload"]

    def test_generate_einvoice_zero_rated(self, strategy):
        sale = MagicMock(spec=["id", "amount_aed", "tax_rate"])
        sale.id = 5
        sale.amount_aed = Decimal("200")
        sale.tax_rate = Decimal("0")
        result = strategy.generate_einvoice(sale)
        assert "<TaxAmount>0</TaxAmount>" in result["xml_payload"]

    def test_resolve_vat_rate_from_sale(self, strategy):
        sale = MagicMock(spec=["tax_rate"])
        sale.tax_rate = Decimal("5")
        assert strategy._resolve_vat_rate(sale) == Decimal("5")


class TestPalestineWPS:
    def test_wps_format_structure(self, strategy):
        employees = [
            {
                "employee_id": "E001",
                "bank_code": "PAL",
                "name": "Ahmad",
                "iban": "PS00BANK0000000000000000000",
                "net_salary": 1500,
            },
        ]
        result = strategy.get_wps_format(employees)
        assert result["format"] == "wps_sif"
        assert result["file_extension"] == ".sif"
        assert result["record_count"] == 1
        assert result["lines"][0].startswith("HDR|")
        assert result["lines"][1].startswith("EDR|E001|")

    def test_wps_not_supported_on_null_strategy(self):
        with pytest.raises(NotImplementedError):
            NullStrategy().get_wps_format([])
