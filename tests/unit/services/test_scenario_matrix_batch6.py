"""Scenario matrix batch 6 — MWAC inventory math + payroll income tax grids.

MWAC invariants: new_qty = old + change; new_value = old_value +
change × unit_cost; average = value/qty. Payroll: AE/SA zero income tax;
IL positive above credit points; PS exempt band.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.stock_service import _MWACHelper
from utils.country_tax import payroll_income_tax_amount


class TestMwacGrid:
    @pytest.mark.parametrize(
        "old_qty,old_value,change,unit_cost,exp_qty,exp_value,exp_avg",
        [
            ("100", "5000", "50", "60", "150", "8000", "53.3333"),
            ("100", "5000", "-50", "60", "50", "2000", "40.0000"),
            ("0", "0", "10", "25", "10", "250", "25.0000"),
            ("10", "250", "-10", "25", "0", "0", "0.0000"),
            ("100", "8000", "100", "80", "200", "16000", "80.0000"),
            ("50", "1000", "50", "40", "100", "3000", "30.0000"),
            ("200", "10000", "-100", "50", "100", "5000", "50.0000"),
            ("25", "750", "25", "30", "50", "1500", "30.0000"),
        ],
    )
    def test_mwac_golden(self, old_qty, old_value, change, unit_cost, exp_qty, exp_value, exp_avg):
        qty, value, avg = _MWACHelper.calc(
            Decimal(old_qty), Decimal(old_value), Decimal(change), Decimal(unit_cost)
        )
        assert qty == Decimal(exp_qty)
        assert value == Decimal(exp_value)
        assert avg == Decimal(exp_avg)


class TestPayrollIncomeTaxGrid:
    @pytest.mark.parametrize("country", ["AE", "SA"])
    @pytest.mark.parametrize("income", ["0", "50000", "200000", "1000000"])
    def test_no_income_tax_countries(self, country, income):
        result = payroll_income_tax_amount(Decimal(income), country)
        assert result["tax"] == Decimal("0.000")

    @pytest.mark.parametrize("income", ["100000", "250000", "500000", "1000000"])
    def test_il_tax_positive_and_below_gross(self, income):
        result = payroll_income_tax_amount(Decimal(income), "IL")
        assert result["tax"] > Decimal("0")
        assert result["tax"] < Decimal(income)

    @pytest.mark.parametrize("income", ["10000", "30000", "48000"])
    def test_ps_exempt_band(self, income):
        result = payroll_income_tax_amount(Decimal(income), "PS")
        assert result["tax"] == Decimal("0.000")

    @pytest.mark.parametrize("income", ["100000", "200000"])
    def test_ps_above_band_positive(self, income):
        result = payroll_income_tax_amount(Decimal(income), "PS")
        assert result["tax"] > Decimal("0")
