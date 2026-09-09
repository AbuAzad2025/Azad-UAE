"""Coverage tests for models/receipt.py uncovered lines/arcs.

Targets:
  lines 84 (base_currency_display), 137 (sale_id/source_type mismatch),
  141 (sale_id/source_id mismatch), 147 (invalid source_type),
  arcs 166->exit (confirm already confirmed), 172->175 (reject already
  unconfirmed), 181->183 (cheque_id link branch), 195->192 (multi-payment
  loop), 235->242 (sale lookup miss -> None).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _make_receipt(**kwargs):
    from models.receipt import Receipt

    base = {
        "receipt_number": "RCV-COV-1",
        "payment_method": "cash",
        "payment_confirmed": True,
        "receipt_date": datetime.now(UTC),
        "amount": Decimal("100"),
        "amount_aed": Decimal("100"),
    }
    base.update(kwargs)
    return Receipt(**base)


class TestBaseCurrencyDisplay:
    def test_line_84_returns_base_currency(self):
        r = _make_receipt()
        r.base_currency = "AED"
        assert r.base_currency_display == "AED"


class TestSaleIdValidator:
    def test_line_137_sale_id_with_manual_source_raises(self):
        from models.receipt import Receipt

        r = Receipt()
        r.source_type = "manual"
        r.source_id = None
        with pytest.raises(ValueError, match="source_type"):
            r.sale_id = 7

    def test_line_141_sale_id_mismatched_source_id_raises(self):
        from models.receipt import Receipt

        r = Receipt()
        r.source_type = "sale"
        r.source_id = 5
        with pytest.raises(ValueError, match="must match source_id"):
            r.sale_id = 6

    def test_sale_id_matching_source_id_passes(self):
        from models.receipt import Receipt

        r = Receipt()
        r.source_type = "sale"
        r.source_id = 5
        r.sale_id = 5
        assert r.sale_id == 5

    def test_sale_id_none_passes(self):
        from models.receipt import Receipt

        r = Receipt()
        r.source_type = "manual"
        r.sale_id = None
        assert r.sale_id is None


class TestSourceTypeValidator:
    def test_line_147_invalid_source_type_raises(self):
        from models.receipt import Receipt

        r = Receipt()
        with pytest.raises(ValueError, match="Invalid source_type"):
            r.source_type = "bogus_xyz"

    def test_valid_source_type_passes(self):
        from models.receipt import Receipt

        r = Receipt()
        r.source_type = "refund"
        assert r.source_type == "refund"


class TestConfirmArc:
    def test_arc_166_exit_already_confirmed_is_noop(self):
        r = _make_receipt(payment_confirmed=True)
        r.confirmation_date = None
        r.confirm_receipt()
        assert r.payment_confirmed is True
        assert r.confirmation_date is None

    def test_confirm_unconfirmed_sets_date(self):
        r = _make_receipt(payment_confirmed=False)
        r.confirm_receipt()
        assert r.payment_confirmed is True
        assert r.confirmation_date is not None


class TestRejectArcs:
    def test_arc_172_175_reject_when_already_unconfirmed(self, mocker):
        mock_payment = mocker.patch("models.Payment")
        mock_payment.query.filter.return_value.all.return_value = []
        r = _make_receipt(payment_confirmed=False)
        r.tenant_id = None
        r.cheque_id = None
        r.reject_receipt("already-rejected")
        assert r.payment_confirmed is False
        assert r.rejection_reason == "already-rejected"

    def test_arc_181_183_reject_with_cheque_id_links_by_cheque(self, mocker):
        sale = MagicMock()
        linked = MagicMock(payment_confirmed=True, sale_id=1, sale=sale)
        mock_payment = mocker.patch("models.Payment")
        mock_payment.query.filter.return_value.all.return_value = [linked]
        r = _make_receipt(payment_confirmed=True)
        r.tenant_id = None
        r.cheque_id = 99
        r.reject_receipt("bounced-cheque")
        assert linked.payment_confirmed is False
        assert linked.rejection_reason == "bounced-cheque"
        sale.recalculate_payment_status.assert_called_once()

    def test_arc_195_192_reject_multiple_payments_loops(self, mocker):
        sale = MagicMock()
        first = MagicMock(payment_confirmed=True, sale_id=1, sale=sale)
        second = MagicMock(payment_confirmed=True, sale_id=None, sale=None)
        mock_payment = mocker.patch("models.Payment")
        mock_payment.query.filter.return_value.all.return_value = [first, second]
        r = _make_receipt(payment_confirmed=True)
        r.tenant_id = None
        r.cheque_id = None
        r.reject_receipt("multi")
        assert first.payment_confirmed is False
        assert first.rejection_reason == "multi"
        assert second.payment_confirmed is False
        sale.recalculate_payment_status.assert_called_once()


class TestGetSourceInfoArc:
    def test_arc_235_242_sale_lookup_miss_returns_none(self, mocker):
        mocker.patch("extensions.db.session.get", return_value=None)
        r = _make_receipt()
        r.source_type = "sale"
        r.source_id = 987654321
        assert r.get_source_info() is None

    def test_get_source_info_sale_hit(self, mocker):
        sale = SimpleNamespace(
            sale_number="S-COV",
            sale_date=datetime(2025, 1, 1),
            total_amount=Decimal("500"),
        )
        mocker.patch("extensions.db.session.get", return_value=sale)
        r = _make_receipt()
        r.source_type = "sale"
        r.source_id = 10
        info = r.get_source_info()
        assert info["number"] == "S-COV"
