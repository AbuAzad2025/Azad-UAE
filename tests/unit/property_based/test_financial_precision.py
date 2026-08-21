"""Property-based tests for financial precision."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from utils.currency_utils import convert_and_quantize_aed


def _dec(value, places=3):
    return Decimal(str(value)).quantize(Decimal("0.1") ** places, rounding=ROUND_HALF_UP)


# Strategies for realistic invoice components.
quantity_st = st.decimals(min_value="0.001", max_value="9999.999", places=3)
price_st = st.decimals(min_value="0.01", max_value="99999.99", places=2)
tax_rate_st = st.decimals(min_value="0", max_value="30", places=2)
discount_rate_st = st.decimals(min_value="0", max_value="100", places=2)
shipping_st = st.decimals(min_value="0", max_value="5000", places=2)
fx_rate_st = st.decimals(min_value="0.10", max_value="10", places=6)


class TestFinancialPrecision:
    @given(
        quantity=quantity_st,
        unit_price=price_st,
        tax_rate=tax_rate_st,
        discount_rate=discount_rate_st,
        shipping=shipping_st,
    )
    @settings(max_examples=200, deadline=None)
    def test_invoice_total_is_non_negative(
        self,
        quantity: Decimal,
        unit_price: Decimal,
        tax_rate: Decimal,
        discount_rate: Decimal,
        shipping: Decimal,
    ):
        """subtotal + tax + shipping - discount is always non-negative for valid inputs."""
        subtotal = (quantity * unit_price).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        discount = (subtotal * (discount_rate / Decimal("100"))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        taxable = subtotal - discount + shipping
        tax = (taxable * (tax_rate / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (taxable + tax).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert total >= Decimal("0")

    @given(
        amount=st.decimals(min_value="0.01", max_value="1000000", places=2),
        rate=fx_rate_st,
    )
    @settings(max_examples=200, deadline=None)
    def test_fx_conversion_followed_by_inverse_is_idempotent(self, amount: Decimal, rate: Decimal):
        """Converting to base and back at the inverse rate stays within rounding tolerance."""
        base = convert_and_quantize_aed(amount, "USD", rate)
        inverted_rate = (Decimal("1") / rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        restored = convert_and_quantize_aed(base, "USD", inverted_rate)
        diff = abs(restored - amount)
        tolerance = max(amount * Decimal("0.0001"), Decimal("0.02"))
        assert diff <= tolerance, f"FX round-trip diff {diff} exceeds tolerance {tolerance}"
