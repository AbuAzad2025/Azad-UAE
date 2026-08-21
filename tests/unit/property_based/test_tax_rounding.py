"""Property-based tests for tax rounding consistency."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from hypothesis import given, settings
from hypothesis import strategies as st


class TestTaxRounding:
    @given(
        lines=st.lists(
            st.tuples(
                st.decimals(min_value="0.01", max_value="9999.99", places=2),
                st.decimals(min_value="1", max_value="100", places=3),
            ),
            min_size=1,
            max_size=20,
        ),
        tax_rate=st.decimals(min_value="0", max_value="30", places=2),
    )
    @settings(max_examples=200, deadline=None)
    def test_per_line_vs_total_tax_rounding_within_tolerance(
        self,
        lines: list[tuple[Decimal, Decimal]],
        tax_rate: Decimal,
    ):
        """Per-line tax rounding and total tax rounding differ by at most one cent per line."""
        rate = tax_rate / Decimal("100")

        per_line_tax = Decimal("0")
        for unit_price, quantity in lines:
            line_total = (unit_price * quantity).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            line_tax = (line_total * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            per_line_tax += line_tax

        subtotal = sum(
            (unit_price * quantity).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) for unit_price, quantity in lines
        )
        total_tax = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        tolerance = Decimal("0.01") * len(lines)
        diff = abs(per_line_tax - total_tax)
        assert diff <= tolerance, f"Tax rounding diff {diff} exceeds {tolerance}"
