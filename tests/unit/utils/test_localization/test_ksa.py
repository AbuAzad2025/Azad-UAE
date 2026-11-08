from __future__ import annotations

import base64
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from utils.localization.ksa import KSAStrategy


@pytest.fixture
def strategy():
    return KSAStrategy()


class TestKSACalculateTax:
    def test_standard_vat(self, strategy):
        result = strategy.calculate_tax(Decimal("100"))
        assert result["tax_amount"] == Decimal("15.00")
        assert result["total_amount"] == Decimal("115.00")
        assert result["rate_applied"] == Decimal("15.00")

    def test_zero_rated(self, strategy):
        result = strategy.calculate_tax(Decimal("250"), tax_rate=Decimal("0"))
        assert result["tax_amount"] == Decimal("0")
        assert result["total_amount"] == Decimal("250")
        assert result["rate_applied"] == Decimal("0")

    def test_custom_rate(self, strategy):
        result = strategy.calculate_tax(Decimal("200"), tax_rate=Decimal("5"))
        assert result["tax_amount"] == Decimal("10.00")
        assert result["total_amount"] == Decimal("210.00")


class TestKSATaxReturn:
    def test_format_tax_return(self, strategy):
        result = strategy.format_tax_return(
            Decimal("1500"),
            Decimal("400"),
            "2025-01-01",
            "2025-01-31",
        )
        assert result["country"] == "SA"
        assert result["net_payable"] == Decimal("1100")
        assert result["format"] == "zatca_vat_v3"
        assert result["currency"] == "SAR"


class TestKSAValidateTaxNumber:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("300000000000003", True),
            ("3-0000-0000-000-003", True),
            ("200000000000003", False),
            ("30000000000000", False),
            ("", False),
            (None, False),
        ],
    )
    def test_trn_validation(self, strategy, value, expected):
        assert strategy.validate_tax_number(value) is expected


class TestKSAEInvoice:
    def _sale(self, total="115", tax="15", currency="SAR"):
        from types import SimpleNamespace

        line = SimpleNamespace(
            quantity=Decimal("1"),
            unit_price=Decimal(str(Decimal(total) - Decimal(tax))),
            line_total=Decimal(str(Decimal(total) - Decimal(tax))),
            product=SimpleNamespace(name="Widget"),
            product_id=1,
        )
        return SimpleNamespace(
            id=42,
            sale_number="INV-KSA-42",
            tenant_id=None,
            customer=SimpleNamespace(name="Buyer", tax_number=""),
            sale_date=None,
            currency=currency,
            tax_rate=Decimal("15"),
            tax_amount=Decimal(tax),
            taxable_amount=Decimal(total) - Decimal(tax),
            subtotal=Decimal(total) - Decimal(tax),
            total_amount=Decimal(total),
            amount_aed=Decimal(total),
            lines=[line],
        )

    def test_generate_einvoice_zatca_simplified(self, strategy):
        result = strategy.generate_einvoice(self._sale())
        assert result["format"] == "zatca_ubl_simplified_xml"
        assert "TaxExclusiveAmount" in result["xml_payload"]
        assert "<cbc:ID>INV-KSA-42</cbc:ID>" in result["xml_payload"]
        tlv = base64.b64decode(result["qr_base64"])
        assert tlv[0] == 1  # TLV tag 1 = seller name
        assert len(result["invoice_hash"]) == 64

    def test_generate_einvoice_zero_rated_sale(self, strategy):
        result = strategy.generate_einvoice(self._sale(total="500", tax="0"))
        assert '<cbc:TaxAmount currencyID="SAR">0.000</cbc:TaxAmount>' in result["xml_payload"]

    def test_amount_aed_not_required(self, strategy):
        sale = self._sale()
        del sale.amount_aed
        result = strategy.generate_einvoice(sale)
        assert len(result["invoice_hash"]) == 64


class TestKSAExtractTax:
    def test_resolve_vat_rate_from_sale(self, strategy):
        sale = MagicMock(spec=["tax_rate"])
        sale.tax_rate = Decimal("5")
        assert strategy._resolve_vat_rate(sale) == Decimal("5")
