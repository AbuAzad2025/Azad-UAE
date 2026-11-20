"""Wave 11 POS toolkit scenarios — change, provenance, and route guards.

These four identifiers close the budget gap created when the register gained
the toolkit routes. Unlike a label-only scenario, each pins an actual contract
of the money path it names.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from services.sale_service import SaleService
from utils.pos_checkout_helpers import _compute_change_due


class TestCashChangeIsNotCredit:
    """POS-89: cash tender above the invoice is change, never customer credit."""

    def test_cash_excess_is_returned_change(self):
        sale = MagicMock()
        sale.amount_aed = Decimal("100")
        change = _compute_change_due(
            sale,
            [{"amount": Decimal("150"), "payment_method": "cash", "currency": "AED", "exchange_rate": Decimal("1")}],
            None,
            "AED",
            Decimal("1"),
            tenant_id=1,
        )
        assert change == Decimal("50")


class TestSplitTenderProvenance:
    """POS-90: every split tender keeps the rate provenance onto its payment."""

    def test_prepared_chunks_carry_rate_source(self):
        chunks = [
            {
                "amount": "30",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
                "rate_source": "open_er_api",
                "rate_fetched_at": "2026-11-20T10:00:00Z",
            }
        ]
        prepared = SaleService.prepare_split_payments(chunks)
        assert prepared[0]["rate_source"] == "open_er_api"
        assert prepared[0]["rate_fetched_at"] == "2026-11-20T10:00:00Z"


class TestRegisteredToolkitApis:
    """POS-91: the register's money actions all exist as real endpoints."""

    def test_toolkit_rules_are_registered(self):
        from app.factory import create_app

        app = create_app()
        rules = {r.rule for r in app.url_map.iter_rules()}
        for rule in (
            "/pos/api/checkout",
            "/pos/api/returns",
            "/pos/api/cash-movements",
            "/pos/api/receipts/lookup",
            "/pos/api/stock/lookup",
            "/pos/api/session/report",
        ):
            assert rule in rules


class TestDrawerExpectedBalance:
    """POS-92: expected drawer nets cash change out exactly once."""

    def test_change_is_subtracted_from_expected_drawer(self):
        from models.pos_session import PosSession

        session = PosSession()
        session.opening_balance_cash = Decimal("500")
        session.total_cash_sales = Decimal("600")
        session.total_change_given = Decimal("40")
        session.total_cash_refunds = Decimal("10")
        session.total_pay_ins = Decimal("25")
        session.total_pay_outs = Decimal("15")
        assert session.compute_expected_balance() == Decimal("1060")
