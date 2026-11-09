"""Unit tests for the per-category output of the VAT return."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from services.tax_service import TaxService


class TestCategoryTotals:
    def test_totals_group_by_category(self, mocker):
        query = MagicMock()
        rows = [
            ("standard", Decimal("100"), "AED", Decimal("1")),
            ("zero", Decimal("40"), "AED", Decimal("1")),
            ("exempt", Decimal("10"), "AED", Decimal("1")),
            ("weird-category", Decimal("5"), "AED", Decimal("1")),
            (None, Decimal("3"), "AED", Decimal("1")),
        ]
        query.outerjoin.return_value = query
        query.filter.return_value = query
        query.all.return_value = rows
        mocker.patch("services.tax_service.db.session.query", return_value=query)
        totals = TaxService._category_sales_totals(1, "2026-01-01", "2026-01-31")
        assert totals["standard"] == 108.0
        assert totals["zero"] == 40.0
        assert totals["exempt"] == 10.0

    def test_no_tenant_returns_zeros(self):
        assert TaxService._category_sales_totals(None, "2026-01-01", "2026-01-31") == {
            "standard": 0.0,
            "zero": 0.0,
            "exempt": 0.0,
        }

    def test_totals_appear_in_vat_return(self, mocker):
        gl_report = {"vat_output": "10", "vat_input": "2", "unresolved_accounts": []}
        mocker.patch("services.gl_service.GLService.get_vat_report", return_value=gl_report)
        mocker.patch.object(TaxService, "_category_sales_totals", return_value={"standard": 120.0, "zero": 0.0, "exempt": 0.0})
        strategy = MagicMock()
        strategy.format_tax_return.return_value = {"output_vat": Decimal("10"), "input_vat": Decimal("2")}
        mocker.patch.object(TaxService, "_get_strategy", return_value=strategy)
        result = TaxService.get_vat_return("2026-01-01", "2026-01-31", tenant_id=1)
        assert result["category_totals"]["standard"] == 120.0
        assert result["output_vat"] == Decimal("10")
