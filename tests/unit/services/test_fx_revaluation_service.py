"""Unit tests for services/fx_revaluation_service.py — unrealized FX revaluation."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

MODULE = "services.fx_revaluation_service"


def _gl_mock(gl):
    gl.get_account_code_for_concept.side_effect = lambda code, **kw: {
        "AR": "1130",
        "AP": "2110",
        "FX_GAIN": "4400",
        "FX_LOSS": "6600",
    }[code]


def _run_revaluate(open_sales=None, open_purchases=None, current_rate="3.5", existing=None):
    entry = MagicMock(id=77)
    with (
        patch(f"{MODULE}.resolve_tenant_base_currency", return_value="AED"),
        patch(f"{MODULE}._posted_period_entries", return_value=existing or []),
        patch(f"{MODULE}._open_sales", return_value=open_sales or []),
        patch(f"{MODULE}._open_purchases", return_value=open_purchases or []),
        patch(f"{MODULE}._current_rate", return_value=Decimal(current_rate)),
        patch(f"{MODULE}.GLService") as gl,
        patch(f"{MODULE}.post_or_fail", return_value=entry) as post,
        patch(f"{MODULE}.atomic_transaction"),
        patch(f"{MODULE}.db"),
    ):
        _gl_mock(gl)
        from services.fx_revaluation_service import revaluate_open_items

        summary = revaluate_open_items(tenant_id=1)
    return summary, post


class TestIdempotency:
    def test_skips_when_period_already_posted(self):
        summary, post = _run_revaluate(
            open_sales=[MagicMock()],
            existing=[7, 8],
        )
        assert summary["skipped_existing_period"] is True
        assert summary["entry_ids"] == [7, 8]
        post.assert_not_called()

    def test_no_open_items_posts_nothing(self):
        summary, post = _run_revaluate()
        assert summary["ar_count"] == 0
        assert summary["ap_count"] == 0
        post.assert_not_called()


class TestArRevaluation:
    def test_open_balance_basis_gain(self):
        sale = MagicMock(
            currency="USD",
            exchange_rate=Decimal("3.0"),
            balance_due=Decimal("300"),
            sale_number="S-1",
        )
        summary, post = _run_revaluate(open_sales=[sale])
        post.assert_called_once()
        lines = post.call_args.args[0]
        # open 300 base @3.0 = 100 USD; revalued @3.5 = 350 → unrealized gain 50
        assert lines[0]["concept_code"] == "AR"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "FX_GAIN"
        assert lines[1]["credit"] == Decimal("50.000")
        assert summary["ar_count"] == 1
        assert summary["ar_diff"] == Decimal("50.000")
        assert summary["entry_ids"] == [77]

    def test_partial_settlement_revalues_only_open_portion(self):
        sale = MagicMock(
            currency="USD",
            exchange_rate=Decimal("3.0"),
            balance_due=Decimal("150"),
            sale_number="S-2",
        )
        summary, post = _run_revaluate(open_sales=[sale])
        post.assert_called_once()
        lines = post.call_args.args[0]
        # only the open half is revalued: 150 base @3.0 = 50 USD → @3.5 = 175 → diff 25
        assert lines[0]["debit"] == Decimal("25.000")
        assert lines[1]["credit"] == Decimal("25.000")
        assert summary["ar_diff"] == Decimal("25.000")

    def test_loss_when_rate_falls(self):
        sale = MagicMock(
            currency="USD",
            exchange_rate=Decimal("3.0"),
            balance_due=Decimal("300"),
            sale_number="S-3",
        )
        summary, post = _run_revaluate(open_sales=[sale], current_rate="2.5")
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["concept_code"] == "FX_LOSS"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "AR"
        assert lines[1]["credit"] == Decimal("50.000")

    def test_skips_when_rate_unchanged(self):
        sale = MagicMock(
            currency="USD",
            exchange_rate=Decimal("3.5"),
            balance_due=Decimal("300"),
            sale_number="S-4",
        )
        summary, post = _run_revaluate(open_sales=[sale], current_rate="3.5")
        post.assert_not_called()
        assert summary["ar_count"] == 0


class TestApRevaluation:
    def test_open_balance_basis_loss(self):
        purchase = MagicMock(
            currency="EUR",
            exchange_rate=Decimal("3.0"),
            purchase_number="P-1",
        )
        summary, post = _run_revaluate(open_purchases=[(purchase, Decimal("300"))])
        post.assert_called_once()
        lines = post.call_args.args[0]
        # open 300 base @3.0 = 100 EUR; revalued @3.5 = 350 → unrealized loss 50
        assert lines[0]["concept_code"] == "FX_LOSS"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "AP"
        assert lines[1]["credit"] == Decimal("50.000")
        assert summary["ap_count"] == 1
        assert summary["ap_diff"] == Decimal("50.000")

    def test_partial_settlement_revalues_only_open_portion(self):
        purchase = MagicMock(
            currency="EUR",
            exchange_rate=Decimal("3.0"),
            purchase_number="P-2",
        )
        summary, post = _run_revaluate(open_purchases=[(purchase, Decimal("150"))])
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["debit"] == Decimal("25.000")
        assert lines[1]["credit"] == Decimal("25.000")
        assert summary["ap_diff"] == Decimal("25.000")

    def test_gain_when_rate_falls(self):
        purchase = MagicMock(
            currency="EUR",
            exchange_rate=Decimal("3.0"),
            purchase_number="P-3",
        )
        summary, post = _run_revaluate(open_purchases=[(purchase, Decimal("300"))], current_rate="2.5")
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["concept_code"] == "AP"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "FX_GAIN"
        assert lines[1]["credit"] == Decimal("50.000")
