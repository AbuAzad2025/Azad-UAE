"""Scenario matrix batch 5 — e-invoice documents, tax strategies, sale math.

Golden cases: UBL totals/hash integrity per country and amount, credit-note
shape, strategy tax math, sale-line totals, and discount guards.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models.sale import SaleLine
from services.sale_service import SaleService
from services.tax_service import TaxService
from utils.country_tax import payroll_income_tax_amount
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash


def _sale(total, tax, taxable=None):
    sale = MagicMock(
        sale_number="S-1",
        sale_date=datetime(2026, 3, 3, 10, 30, 0),
        tax_rate=Decimal("5"),
        total_amount=Decimal(str(total)),
        tax_amount=Decimal(str(tax)),
        taxable_amount=Decimal(str(taxable)) if taxable is not None else Decimal(str(total)) - Decimal(str(tax)),
        subtotal=Decimal(str(total)),
        lines=[],
    )
    sale.customer = MagicMock(name="Buyer", tax_number="")
    return sale


def _tenant():
    return MagicMock(name="Seller Co", name_en="Seller Co", tax_number="123", address_en="", city="")


class TestEinvoiceDocuments:
    @pytest.mark.parametrize(
        "country,total,tax",
        [("AE", "105", "5"), ("PS", "116", "16"), ("IL", "118", "18"), ("SA", "115", "15")],
    )
    def test_invoice_totals_and_hash(self, country, total, tax):
        xml = build_invoice_xml(_sale(total, tax), _tenant(), country=country, currency="AED")
        assert f"{Decimal(total):.3f}" in xml
        assert f"{Decimal(tax):.3f}" in xml
        digest = invoice_hash(xml)
        assert len(digest) == 64
        assert invoice_hash(xml) == digest

    @pytest.mark.parametrize("total", ["100", "200", "999.99"])
    def test_hash_changes_with_amount(self, total):
        a = build_invoice_xml(_sale(total, "5"), _tenant(), country="AE", currency="AED")
        b = build_invoice_xml(_sale(str(Decimal(total) + 1), "5"), _tenant(), country="AE", currency="AED")
        assert invoice_hash(a) != invoice_hash(b)

    def test_credit_note_shape(self):
        xml = build_invoice_xml(
            _sale("105", "5"), _tenant(), country="AE", currency="AED",
            doc_type="credit_note", billing_reference="S-ORIG",
        )
        assert "381" in xml
        assert "S-ORIG" in xml


class TestTaxStrategies:
    @pytest.mark.parametrize(
        "code,amount,rate,expected_tax",
        [
            ("AE", "1000", "5", "50.000"),
            ("PS", "1000", "16", "160.000"),
            ("IL", "1000", "18", "180.000"),
            ("SA", "1000", "15", "150.000"),
            ("AE", "333.33", "5", "16.67"),
            ("PS", "0", "16", "0.000"),
        ],
    )
    def test_strategy_calculate(self, code, amount, rate, expected_tax):
        strategy = TaxService._get_strategy(tenant_id=None)
        result = strategy.calculate_tax(Decimal(amount), Decimal(rate))
        assert Decimal(str(result["tax_amount"])) == Decimal(expected_tax)


class TestSaleLineTotals:
    @pytest.mark.parametrize(
        "qty,price,disc,expected",
        [
            ("2", "50", "0", "100.000"), ("3", "33.33", "10", "89.991"),
            ("1", "100", "50", "50.000"), ("10", "9.99", "0", "99.900"),
            ("5", "20", "25", "75.000"), ("0", "100", "0", "0.000"),
        ],
    )
    def test_line_total_golden(self, qty, price, disc, expected):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        assert line.line_total == Decimal(expected)


class TestDiscountGuard:
    @pytest.mark.parametrize("discount,subtotal,ok", [("50", "100", True), ("100", "100", True), ("101", "100", False)])
    def test_discount_within_subtotal(self, discount, subtotal, ok):
        if ok:
            SaleService._ensure_discount_within_subtotal(Decimal(discount), Decimal(subtotal))
        else:
            with pytest.raises(ValueError):
                SaleService._ensure_discount_within_subtotal(Decimal(discount), Decimal(subtotal))


class TestPayrollIncomeTax:
    @pytest.mark.parametrize(
        "country,income,expect_zero",
        [("AE", "100000", True), ("SA", "100000", True), ("PS", "10000", True)],
    )
    def test_no_or_exempt_income_tax(self, country, income, expect_zero):
        result = payroll_income_tax_amount(Decimal(income), country)
        if expect_zero:
            assert result["tax"] == Decimal("0.000")

    def test_il_high_income_tax_positive(self):
        result = payroll_income_tax_amount(Decimal("500000"), "IL")
        assert result["tax"] > Decimal("0")
        assert result["effective_rate"] > Decimal("0")
