"""Scenario matrix batch 3 — statutory payroll, guards, and document integrity.

Golden grids computed from the published statutory tables in
``utils/country_tax.py`` (PS NSSF 7/9 capped 18,800; SA GOSI post-2024
10.25/12.25, non-national employer 2%; AE GPSSA nationals 11/15 capped
70,000), plus range guards and document hash integrity.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from routes.partners import _parse_partner_financials
from services.gl_posting import GlPostingError, assert_balanced_lines
from services.ita_allocation_service import ItaAllocationService
from services.partner_service import PartnerService
from utils.country_tax import social_insurance_amount


class TestSocialInsurancePs:
    @pytest.mark.parametrize(
        "gross,employee,employer",
        [
            ("10000", "700.000", "900.000"),
            ("5000", "350.000", "450.000"),
            ("18800", "1316.000", "1692.000"),
            ("20000", "1316.000", "1692.000"),
            ("30000", "1316.000", "1692.000"),
            ("1000", "70.000", "90.000"),
            ("7522", "526.540", "676.980"),
        ],
    )
    def test_ps_nssf(self, gross, employee, employer):
        result = social_insurance_amount(Decimal(gross), "PS")
        assert result["employee"] == Decimal(employee)
        assert result["employer"] == Decimal(employer)


class TestSocialInsuranceSa:
    @pytest.mark.parametrize(
        "gross,national,employee,employer",
        [
            ("10000", True, "1025.000", "1225.000"),
            ("10000", False, "0.000", "200.000"),
            ("45000", True, "4612.500", "5512.500"),
            ("60000", True, "4612.500", "5512.500"),
            ("3000", True, "307.500", "367.500"),
        ],
    )
    def test_sa_gosi(self, gross, national, employee, employer):
        result = social_insurance_amount(Decimal(gross), "SA", is_national=national, joined_2024_07_03_or_later=True)
        assert result["employee"] == Decimal(employee)
        assert result["employer"] == Decimal(employer)


class TestSocialInsuranceAe:
    @pytest.mark.parametrize(
        "gross,national,employee,employer",
        [
            ("10000", True, "1100.000", "1500.000"),
            ("10000", False, "0.000", "0.000"),
            ("70000", True, "7700.000", "10500.000"),
            ("80000", True, "7700.000", "10500.000"),
            ("5000", True, "550.000", "750.000"),
        ],
    )
    def test_ae_gpssa(self, gross, national, employee, employer):
        result = social_insurance_amount(Decimal(gross), "AE", is_national=national)
        assert result["employee"] == Decimal(employee)
        assert result["employer"] == Decimal(employer)


class TestBalancedLinesGuard:
    @pytest.mark.parametrize("amount", ["10", "100.50", "0.001", "999.99", "5000.25"])
    def test_balanced_passes(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize("debit,credit", [("100", "99"), ("0.01", "0.02"), ("500", "0")])
    def test_unbalanced_raises(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestPartnerFinancialRanges:
    def _form(self, **overrides):
        form = {
            "investment_amount": "0",
            "share_percentage": "10",
            "fixed_monthly_amount": "0",
            "expense_share_percentage": "0",
            "loss_share_percentage": "0",
            "min_profit_threshold": "0",
        }
        form.update(overrides)
        return form

    @pytest.mark.parametrize(
        "field,bad",
        [
            ("share_percentage", "101"),
            ("share_percentage", "-1"),
            ("expense_share_percentage", "150"),
            ("loss_share_percentage", "100.01"),
            ("investment_amount", "-5"),
            ("fixed_monthly_amount", "-1"),
            ("min_profit_threshold", "-0.01"),
            ("share_percentage", "abc"),
        ],
    )
    def test_out_of_range_refused(self, field, bad):
        values, error = _parse_partner_financials(self._form(**{field: bad}))
        assert values is None
        assert error

    @pytest.mark.parametrize("share", ["0", "50", "100", "33.33"])
    def test_valid_shares_accepted(self, share):
        values, error = _parse_partner_financials(self._form(share_percentage=share))
        assert error is None
        assert values["share_percentage"] == Decimal(share)


class TestMonthsAndWindows:
    @pytest.mark.parametrize(
        "start,end,expected",
        [
            (date(2026, 1, 1), date(2026, 1, 31), 1),
            (date(2026, 1, 1), date(2026, 3, 31), 3),
            (date(2025, 12, 15), date(2026, 2, 10), 3),
            (date(2026, 6, 1), date(2026, 6, 30), 1),
            (date(2026, 1, 31), date(2026, 1, 1), 1),
        ],
    )
    def test_months_in_period(self, start, end, expected):
        assert PartnerService._months_in_period(start, end) == expected

    @pytest.mark.parametrize(
        "start,end,expected_days",
        [
            (None, None, 31),
            (date(2026, 1, 16), None, 16),
            (None, date(2026, 1, 15), 15),
            (date(2026, 1, 10), date(2026, 1, 20), 11),
        ],
    )
    def test_active_window_days(self, start, end, expected_days):
        partner = MagicMock(start_date=start, end_date=end)
        window = PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 1, 31))
        assert window is not None
        assert (window[1] - window[0]).days + 1 == expected_days

    def test_no_overlap_returns_none(self):
        partner = MagicMock(start_date=date(2026, 3, 1), end_date=None)
        assert PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 1, 31)) is None


class TestItaPayloadVariants:
    def _sale(self, **overrides):
        base = {
            "sale_number": "S-1",
            "taxable_amount": Decimal("100"),
            "tax_amount": Decimal("18"),
            "total_amount": Decimal("118"),
            "discount_amount": Decimal("0"),
            "subtotal": Decimal("100"),
            "sale_date": None,
        }
        base.update(overrides)
        return MagicMock(**base)

    @pytest.mark.parametrize(
        "subtotal,discount,expected_before",
        [("100", "0", "100.00"), ("150", "50", "150.00"), ("0", "0", "100.00")],
    )
    def test_before_discount_derivation(self, subtotal, discount, expected_before):
        payload = ItaAllocationService._build_payload(
            MagicMock(id=1),
            self._sale(subtotal=Decimal(subtotal), discount_amount=Decimal(discount)),
            "123456789",
            "",
        )
        assert payload["Amount_Before_Discount"] == expected_before
        assert payload["Discount"] == f"{abs(Decimal(discount)):.2f}"

    def test_buyer_omitted_when_empty(self):
        payload = ItaAllocationService._build_payload(MagicMock(id=1), self._sale(), "123456789", "")
        assert "Customer_VAT_Number" not in payload
