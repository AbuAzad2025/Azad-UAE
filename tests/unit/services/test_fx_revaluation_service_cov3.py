"""Coverage boost for services/fx_revaluation_service.py.

Targets the helpers and fallback branches missed by the base suite:
_current_rate None path (36-44), _open_sales/_open_purchases (47-76),
_posted_period_entries (79-91), AR/AP no-rate + zero-original + tiny-balance
+ tiny-diff guards (194-200/207-208/218-219, 262-269/275-277/287-288), and
reverse_previous_revaluation (324-353). Real service functions run; DB/rate
boundaries are mocked.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

MODULE = "services.fx_revaluation_service"


def _chain(**kwargs):
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = kwargs.get("all_result", [])
    return q


class TestCurrentRate:
    def test_returns_decimal_when_resolved(self):
        with patch(
            f"{MODULE}.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": "3.5"},
        ):
            from services.fx_revaluation_service import _current_rate

            assert _current_rate("USD", "AED", 1) == Decimal("3.5")

    def test_returns_none_when_rate_missing(self):
        with patch(
            f"{MODULE}.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": None},
        ):
            from services.fx_revaluation_service import _current_rate

            assert _current_rate("USD", "AED", 1) is None


class TestOpenQueries:
    def test_open_sales_filters_by_tenant(self):
        from services import fx_revaluation_service as fx

        sale = MagicMock(id=1)
        q = _chain(all_result=[sale])
        # Sale is imported lazily inside _open_sales; patch models.Sale.query instead
        with patch("models.Sale.query", new=q):
            assert fx._open_sales(7, "AED") == [sale]
        assert q.filter.call_count == 2

    def test_open_sales_without_tenant_skips_tenant_filter(self):
        from services import fx_revaluation_service as fx

        q = _chain(all_result=[])
        with patch("models.Sale.query", new=q):
            assert fx._open_sales(None, "AED") == []
        assert q.filter.call_count == 1

    def test_open_purchases_keeps_only_positive_balances(self):
        from services import fx_revaluation_service as fx

        full = MagicMock(amount_aed=Decimal("500"), currency="USD")
        full.get_paid_amount.return_value = Decimal("100")
        zero = MagicMock(amount_aed=Decimal("50"), currency="USD")
        zero.get_paid_amount.return_value = Decimal("50")
        q = _chain(all_result=[full, zero])
        with patch("models.Purchase.query", new=q):
            rows = fx._open_purchases(9, "AED")
        assert len(rows) == 1
        assert rows[0][0] is full
        assert rows[0][1] == Decimal("400")

    def test_open_purchases_without_tenant(self):
        from services import fx_revaluation_service as fx

        q = _chain(all_result=[])
        with patch("models.Purchase.query", new=q):
            assert fx._open_purchases(None, "AED") == []
        assert q.filter.call_count == 1

    def test_posted_period_entries_with_and_without_tenant(self):
        from services import fx_revaluation_service as fx

        e1, e2 = MagicMock(id=11), MagicMock(id=12)
        q = _chain(all_result=[e1, e2])
        with patch("models.gl.GLJournalEntry.query", new=q):
            assert fx._posted_period_entries("2026-09", 3) == [11, 12]
        assert q.filter.call_count == 2
        q2 = _chain(all_result=[])
        with patch("models.gl.GLJournalEntry.query", new=q2):
            assert fx._posted_period_entries("2026-09", None) == []
        assert q2.filter.call_count == 1


def _revaluate(open_sales=None, open_purchases=None, rates=None):
    entry = MagicMock(id=99)
    rate_map = rates or {}

    def _rate(cur, base, tenant_id):
        return rate_map.get(cur, Decimal("3.5"))

    with (
        patch(f"{MODULE}.resolve_tenant_base_currency", return_value="AED"),
        patch(f"{MODULE}._posted_period_entries", return_value=[]),
        patch(f"{MODULE}._open_sales", return_value=open_sales or []),
        patch(f"{MODULE}._open_purchases", return_value=open_purchases or []),
        patch(f"{MODULE}._current_rate", side_effect=_rate),
        patch(f"{MODULE}.GLService") as gl,
        patch(f"{MODULE}.post_or_fail", return_value=entry) as post,
        patch(f"{MODULE}.atomic_transaction"),
        patch(f"{MODULE}.db"),
    ):
        gl.get_account_code_for_concept.side_effect = lambda code, **kw: {
            "AR": "1130",
            "AP": "2110",
            "FX_GAIN": "4400",
            "FX_LOSS": "6600",
        }[code]
        from services.fx_revaluation_service import revaluate_open_items

        summary = revaluate_open_items(tenant_id=1)
    return summary, post


def _sale(**kw):
    base = {
        "currency": "USD",
        "exchange_rate": Decimal("3.0"),
        "balance_due": Decimal("300"),
        "sale_number": "S-9",
        "id": 5,
        "branch_id": 2,
    }
    base.update(kw)
    return MagicMock(**base)


def _purchase(balance=Decimal("300"), **kw):
    base = {
        "currency": "EUR",
        "exchange_rate": Decimal("3.0"),
        "purchase_number": "P-9",
        "id": 6,
        "branch_id": 2,
    }
    base.update(kw)
    return MagicMock(**base), balance


class TestArFallbackBranches:
    def test_no_rate_records_error_and_skips(self):
        summary, post = _revaluate(open_sales=[_sale()], rates={"USD": None})
        post.assert_not_called()
        assert summary["ar_count"] == 0
        assert any("USD" in e for e in summary["errors"])

    def test_zero_original_rate_treated_as_one(self):
        summary, post = _revaluate(open_sales=[_sale(exchange_rate=Decimal("0"))])
        post.assert_called_once()
        assert summary["ar_count"] == 1

    def test_negative_original_rate_treated_as_one(self):
        summary, post = _revaluate(open_sales=[_sale(exchange_rate=Decimal("-2"))])
        post.assert_called_once()

    def test_tiny_open_balance_skipped(self):
        summary, post = _revaluate(open_sales=[_sale(balance_due=Decimal("0.005"))])
        post.assert_not_called()
        assert summary["ar_count"] == 0

    def test_tiny_diff_skipped(self):
        # current barely above original so the quantized diff rounds to ~0.000;
        # use a small balance so diff stays under the 0.01 threshold
        summary, post = _revaluate(
            open_sales=[_sale(balance_due=Decimal("1"), exchange_rate=Decimal("3.5"))],
            rates={"USD": Decimal("3.501")},
        )
        post.assert_not_called()
        assert summary["ar_count"] == 0


class TestApFallbackBranches:
    def test_no_rate_records_error_and_skips(self):
        purchase, bal = _purchase()
        summary, post = _revaluate(open_purchases=[(purchase, bal)], rates={"EUR": None})
        post.assert_not_called()
        assert summary["ap_count"] == 0
        assert any("EUR" in e for e in summary["errors"])

    def test_negative_original_rate_treated_as_one(self):
        purchase, bal = _purchase()
        purchase.exchange_rate = Decimal("-2")
        summary, post = _revaluate(open_purchases=[(purchase, bal)])
        post.assert_called_once()
        assert summary["ap_count"] == 1

    def test_skips_when_rate_unchanged(self):
        purchase, bal = _purchase()
        purchase.exchange_rate = Decimal("3.5")
        summary, post = _revaluate(open_purchases=[(purchase, bal)], rates={"EUR": Decimal("3.5")})
        post.assert_not_called()
        assert summary["ap_count"] == 0

    def test_tiny_open_balance_skipped(self):
        purchase, bal = _purchase(balance=Decimal("0.005"))
        summary, post = _revaluate(open_purchases=[(purchase, bal)])
        post.assert_not_called()

    def test_tiny_diff_skipped(self):
        purchase, bal = _purchase(balance=Decimal("1"))
        purchase.exchange_rate = Decimal("3.5")
        summary, post = _revaluate(open_purchases=[(purchase, bal)], rates={"EUR": Decimal("3.501")})
        post.assert_not_called()
        assert summary["ap_count"] == 0

    def test_ap_gain_posts_ap_debit(self):
        purchase, bal = _purchase()
        summary, post = _revaluate(open_purchases=[(purchase, bal)], rates={"EUR": Decimal("2.5")})
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["concept_code"] == "AP"
        assert summary["ap_diff"] == Decimal("-50.000")


class TestReversePrevious:
    def test_reverses_all_posted_entries(self):
        from services import fx_revaluation_service as fx

        e1 = MagicMock(id=21)
        rev = MagicMock(id=31)
        e1.reverse_entry.return_value = rev
        q = _chain(all_result=[e1])
        with (
            patch("models.gl.GLJournalEntry.query", new=q),
            patch(f"{MODULE}.atomic_transaction"),
        ):
            out = fx.reverse_previous_revaluation("2026-08", tenant_id=4)
        assert out == [31]
        e1.reverse_entry.assert_called_once()
        assert q.filter.call_count == 2

    def test_reverse_without_tenant_and_empty(self):
        from services import fx_revaluation_service as fx

        q = _chain(all_result=[])
        with (
            patch("models.gl.GLJournalEntry.query", new=q),
            patch(f"{MODULE}.atomic_transaction"),
        ):
            assert fx.reverse_previous_revaluation("2026-08") == []
        assert q.filter.call_count == 1
