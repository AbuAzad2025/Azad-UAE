"""Coverage tests for models/sale.py uncovered lines/arcs.

Targets:
  lines 130 (base_currency_for_display), 144 (base_currency_display),
  181 (effective_rep_id), 186-196 (effective_rep_name branches),
  arcs 285->291 (no returns attr), 287->286 (unapproved return),
  298->293 (unconfirmed non-cheque), 309-310 (exchange-rate fallback),
  342->340 (pending-cheque loop mix), 354->353 (confirmed loop mix),
  461->465 (SaleLine.to_dict without cost).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock


def _sale():
    from models.sale import Sale

    s = Sale()
    s.amount_aed = Decimal("100")
    s.currency = "AED"
    s.base_currency = "AED"
    s.exchange_rate = Decimal("1")
    s.tenant_id = 1
    return s


def _pay(amount, confirmed=True, method="cash"):
    p = MagicMock()
    p.payment_confirmed = confirmed
    p.payment_method = method
    p.amount_aed = Decimal(str(amount))
    return p


def _ret(amount, status="approved"):
    r = MagicMock()
    r.status = status
    r.amount_aed = Decimal(str(amount))
    return r


class TestDisplayAliases:
    def test_line_130_base_currency_set(self):
        s = _sale()
        s.base_currency = "AED"
        s.currency = "USD"
        assert s.base_currency_for_display == "AED"

    def test_line_130_base_currency_fallback_to_currency(self):
        s = _sale()
        s.base_currency = None
        s.currency = "USD"
        assert s.base_currency_for_display == "USD"

    def test_line_144_base_currency_display(self):
        s = _sale()
        s.base_currency = "AED"
        assert s.base_currency_display == "AED"


class TestEffectiveRepId:
    def test_line_181_with_sales_rep(self):
        s = _sale()
        s.sales_rep_id = 9
        s.seller_id = 3
        assert s.effective_rep_id == 9

    def test_line_181_fallback_to_seller(self):
        s = _sale()
        s.sales_rep_id = None
        s.seller_id = 3
        assert s.effective_rep_id == 3


class TestEffectiveRepName:
    def test_line_186_sales_rep_name_wins(self):
        s = _sale()
        s.sales_rep_name = "External Agent"
        assert s.effective_rep_name == "External Agent"

    def test_lines_188_193_sales_rep_with_display_name(self):
        s = _sale()
        s.sales_rep_name = None
        rep = MagicMock()
        rep.get_display_name.return_value = "Rep Display"
        s.sales_rep = rep
        assert s.effective_rep_name == "Rep Display"

    def test_lines_188_193_sales_rep_without_display_name(self):
        s = _sale()
        s.sales_rep_name = None
        s.sales_rep = SimpleNamespace(username="repuser")
        assert s.effective_rep_name == "repuser"

    def test_lines_194_195_seller_with_display_name(self):
        s = _sale()
        s.sales_rep_name = None
        s.sales_rep = None
        seller = MagicMock()
        seller.get_display_name.return_value = "Seller Display"
        s.seller = seller
        assert s.effective_rep_name == "Seller Display"

    def test_lines_194_195_seller_without_display_name(self):
        s = _sale()
        s.sales_rep_name = None
        s.sales_rep = None
        # Bypass the seller back_populates descriptor so a plain stub
        # without get_display_name exercises the username fallback.
        s.__dict__["seller"] = SimpleNamespace(username="selleruser")
        assert s.effective_rep_name == "selleruser"

    def test_line_196_no_rep_no_seller_returns_none(self):
        s = _sale()
        s.sales_rep_name = None
        s.sales_rep = None
        s.seller = None
        assert s.effective_rep_name is None


class TestRecalculateArcs:
    def test_arc_285_291_no_returns_attribute(self):
        from models.sale import Sale

        stub = SimpleNamespace(
            payments=[],
            amount_aed=Decimal("100"),
            currency="AED",
            base_currency="AED",
            exchange_rate=Decimal("1"),
        )
        Sale.recalculate_payment_status(stub)
        assert stub.payment_status == "unpaid"
        assert stub.balance_due == Decimal("100.000")

    def test_arc_287_286_unapproved_return_skipped(self):
        s = _sale()
        s.payments = []
        s.returns = [_ret("20", status="draft"), _ret("30", status="approved")]
        s.recalculate_payment_status()
        assert s.payment_status == "partial"
        assert s.balance_due == Decimal("70.000")

    def test_arc_298_293_unconfirmed_cash_ignored(self):
        s = _sale()
        s.payments = [_pay("50", confirmed=False, method="cash"), _pay("10")]
        s.returns = []
        s.recalculate_payment_status()
        assert s.payment_status == "partial"
        assert s.balance_due == Decimal("90.000")

    def test_arc_309_310_bad_exchange_rate_fallback(self):
        s = _sale()
        s.currency = "USD"
        s.base_currency = "AED"
        s.exchange_rate = "bad"
        s.paid_amount = None
        s.payments = [_pay("10")]
        s.returns = []
        s.recalculate_payment_status()
        assert s.paid_amount == Decimal("0")
        assert s.payment_status == "partial"

    def test_recalculate_unpaid_status(self):
        s = _sale()
        s.payments = []
        s.returns = []
        s.recalculate_payment_status()
        assert s.payment_status == "unpaid"


class TestAmountLoops:
    def test_arc_342_340_pending_cheques_mixed(self):
        s = _sale()
        s.payments = [
            _pay("10", confirmed=True, method="cash"),
            _pay("30", confirmed=False, method="cheque"),
        ]
        assert s.pending_cheques_amount == Decimal("30")

    def test_arc_354_353_confirmed_mixed(self):
        s = _sale()
        s.payments = [
            _pay("75", confirmed=True, method="cash"),
            _pay("25", confirmed=False, method="cash"),
        ]
        assert s.confirmed_payments_amount == Decimal("75")


class TestSaleLineToDict:
    def test_arc_461_465_without_cost(self):
        from models.sale import SaleLine

        line = SaleLine()
        line.id = 2
        line.product = MagicMock(name="Part")
        line.quantity = Decimal("1")
        line.unit_price = Decimal("10")
        line.discount_percent = Decimal("0")
        line.line_total = Decimal("10")
        line.cost_price = Decimal("5")
        data = line.to_dict()
        assert data["line_total"] == 10.0
        assert "profit" not in data
        assert "cost_price" not in data
