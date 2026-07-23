"""Fast-cash key computation — Decimal-exact thresholds and change math."""

from __future__ import annotations

from decimal import Decimal

import pytest

from utils.pos_helpers import compute_fast_cash_options


class TestFastCashThresholds:
    def test_exact_amount_first_with_zero_change(self):
        options = compute_fast_cash_options("37", currency="AED")
        assert options[0] == {"amount": Decimal("37.000"), "change": Decimal("0.000"), "is_exact": True}

    def test_aed_round_up_denominations(self):
        options = compute_fast_cash_options("37", currency="AED")
        amounts = [o["amount"] for o in options]
        assert amounts == [
            Decimal("37.000"),
            Decimal("40.000"),
            Decimal("50.000"),
            Decimal("100.000"),
            Decimal("200.000"),
            Decimal("500.000"),
            Decimal("1000.000"),
        ]

    def test_change_math_is_decimal_exact(self):
        options = compute_fast_cash_options("37", currency="AED")
        by_amount = {o["amount"]: o["change"] for o in options}
        assert by_amount[Decimal("40.000")] == Decimal("3.000")
        assert by_amount[Decimal("50.000")] == Decimal("13.000")
        assert by_amount[Decimal("1000.000")] == Decimal("963.000")

    def test_exact_note_multiple_not_duplicated(self):
        options = compute_fast_cash_options("40", currency="AED")
        amounts = [o["amount"] for o in options]
        assert amounts.count(Decimal("40.000")) == 1
        assert amounts[0] == Decimal("40.000")
        assert options[0]["is_exact"] is True
        assert all(o["amount"] > Decimal("40.000") for o in options[1:])

    def test_zero_total_returns_exact_only(self):
        options = compute_fast_cash_options("0", currency="AED")
        assert len(options) == 1
        assert options[0]["amount"] == Decimal("0.000")
        assert options[0]["is_exact"] is True

    def test_fractional_total_thousands_precision(self):
        options = compute_fast_cash_options("7.555", currency="AED")
        assert options[0]["amount"] == Decimal("7.555")
        by_amount = {o["amount"]: o["change"] for o in options}
        assert by_amount[Decimal("10.000")] == Decimal("2.445")

    def test_small_fractional_total(self):
        options = compute_fast_cash_options("0.300", currency="AED")
        by_amount = {o["amount"]: o["change"] for o in options}
        assert by_amount[Decimal("5.000")] == Decimal("4.700")

    def test_ils_denominations(self):
        options = compute_fast_cash_options("30", currency="ILS")
        amounts = [o["amount"] for o in options]
        assert amounts == [
            Decimal("30.000"),
            Decimal("40.000"),
            Decimal("50.000"),
            Decimal("100.000"),
            Decimal("200.000"),
        ]

    def test_unknown_currency_falls_back_to_aed_ladder(self):
        options = compute_fast_cash_options("37", currency="XYZ")
        amounts = [o["amount"] for o in options]
        assert Decimal("40.000") in amounts
        assert Decimal("50.000") in amounts

    def test_case_insensitive_currency(self):
        lower = compute_fast_cash_options("30", currency="ils")
        upper = compute_fast_cash_options("30", currency="ILS")
        assert [o["amount"] for o in lower] == [o["amount"] for o in upper]

    def test_max_options_cap(self):
        options = compute_fast_cash_options("1", currency="AED", max_options=3)
        assert len(options) == 3

    def test_negative_total_rejected(self):
        with pytest.raises(ValueError, match="سالب"):
            compute_fast_cash_options("-5", currency="AED")

    def test_all_options_cover_total(self):
        for total in ("12.75", "99.999", "250", "1000", "3"):
            options = compute_fast_cash_options(total, currency="AED")
            total_dec = Decimal(total).quantize(Decimal("0.001"))
            for option in options:
                assert option["amount"] >= total_dec
                assert option["amount"] - total_dec == option["change"]
