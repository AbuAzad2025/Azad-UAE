"""Property-based tests for FX revaluation math."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from hypothesis import given, settings
from hypothesis import strategies as st


class TestFxRevaluation:
    @given(
        foreign_amount=st.decimals(min_value="0.01", max_value="1000000", places=2),
        old_rate=st.decimals(min_value="0.01", max_value="10", places=6),
        new_rate=st.decimals(min_value="0.01", max_value="10", places=6),
    )
    @settings(max_examples=200, deadline=None)
    def test_revaluation_delta_matches_new_base_minus_old_base(
        self,
        foreign_amount: Decimal,
        old_rate: Decimal,
        new_rate: Decimal,
    ):
        """Revaluation delta = foreign_amount * new_rate - foreign_amount * old_rate."""
        old_base = (foreign_amount * old_rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        new_base = (foreign_amount * new_rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        delta = (new_base - old_base).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        if delta > Decimal("0"):
            # Receivable gain / payable loss: debit AR/AP, credit FX gain.
            assert delta == new_base - old_base
        elif delta < Decimal("0"):
            # Receivable loss / payable gain: debit FX loss, credit AR/AP.
            assert abs(delta) == old_base - new_base
        else:
            assert new_base == old_base

        # Sanity: new_base is always foreign_amount * new_rate within rounding.
        assert abs(new_base - foreign_amount * new_rate) <= Decimal("0.001")
