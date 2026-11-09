"""Unit tests for the per-category output of the VAT return."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from services.tax_service import TaxService


class TestCategoryTotals:
    def test_unreliable_category_totals_are_not_presented_as_net_sales(self, mocker):
        gl_report = {"vat_output": "10", "vat_input": "2", "unresolved_accounts": []}
        mocker.patch("services.gl_service.GLService.get_vat_report", return_value=gl_report)
        strategy = MagicMock()
        strategy.format_tax_return.return_value = {"output_vat": Decimal("10"), "input_vat": Decimal("2")}
        mocker.patch.object(TaxService, "_get_strategy", return_value=strategy)
        result = TaxService.get_vat_return("2026-01-01", "2026-01-31", tenant_id=1)
        assert result["category_totals"] is None
        assert result["output_vat"] == Decimal("10")
