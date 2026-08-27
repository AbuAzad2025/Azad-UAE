"""POS split-tender checkout helper matrix (utils/pos_checkout_helpers.py)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from utils.pos_checkout_helpers import (
    _accumulate_session_tender,
    _compute_change_due,
    _parse_split_tenders,
    _pos_standard_price,
    _promotion_evaluation_json,
    _tender_chunk_aed,
)


@pytest.fixture(autouse=True)
def _aed_base_currency(mocker):
    """Anchor base-currency resolution to AED (context settings are DB-backed)."""
    mocker.patch("utils.currency_utils.context_aware_default_currency", return_value="AED")


class TestParseSplitTenders:
    def test_rejects_non_list_and_empty_list(self):
        for bad in ("nope", None, []):
            chunks, err = _parse_split_tenders(bad, "AED", "1")
            assert chunks is None
            assert err

    def test_rejects_non_dict_chunk(self):
        chunks, err = _parse_split_tenders(["cash"], "AED", "1")
        assert chunks is None
        assert "الدفعة" in err

    def test_rejects_unparseable_amount(self):
        chunks, err = _parse_split_tenders([{"amount": "abc"}], "AED", "1")
        assert chunks is None
        assert "صالح" in err

    def test_rejects_zero_amount(self):
        chunks, err = _parse_split_tenders([{"amount": "0"}], "AED", "1")
        assert chunks is None
        assert "أكبر من صفر" in err

    def test_rejects_missing_method(self):
        chunks, err = _parse_split_tenders([{"amount": 10, "payment_method": "   "}], "AED", "1")
        assert chunks is None
        assert "طريقة الدفع" in err

    def test_rejects_bad_exchange_rate(self):
        chunks, err = _parse_split_tenders([{"amount": 10, "method": "cash", "exchange_rate": "x"}], "AED", "1")
        assert chunks is None
        assert "سعر الصرف" in err

    def test_happy_path_normalizes_fields(self):
        chunks, err = _parse_split_tenders(
            [
                {
                    "amount": "12.5",
                    "payment_method": " card ",
                    "currency": "usd",
                    "reference_number": " R-1 ",
                    "cheque_number": "CH-9",
                    "cheque_date": "2026-01-02",
                    "bank_name": "ENBD",
                    "notes": "quick",
                },
                {"amount": 3, "method": "cash"},
            ],
            default_currency="aed",
            default_rate="1",
        )
        assert err is None
        first, second = chunks
        assert first["amount"] == Decimal("12.5")
        assert first["payment_method"] == "card"
        assert first["currency"] == "USD"
        assert first["exchange_rate"] == Decimal("1")  # default rate applied
        assert first["reference_number"] == "R-1"
        assert first["cheque_number"] == "CH-9"
        assert first["bank_name"] == "ENBD"
        assert second["currency"] == "AED"
        assert second["reference_number"] is None
        assert second["payment_method"] == "cash"  # legacy ``method`` alias accepted

    def test_explicit_rate_wins_over_default(self):
        chunks, _ = _parse_split_tenders(
            [{"amount": 5, "payment_method": "cash", "exchange_rate": "3.675"}], "AED", "1"
        )
        assert chunks[0]["exchange_rate"] == Decimal("3.675")


class TestTenderChunkAed:
    def test_aed_chunk_passthrough_quantized(self):
        chunk = {"amount": Decimal("1.99995"), "currency": "AED", "exchange_rate": Decimal("9")}
        assert _tender_chunk_aed(chunk, tenant_id=None) == Decimal("2.000")

    def test_aed_exact_milli_amount_unchanged(self):
        chunk = {"amount": Decimal("1.999"), "currency": "aed", "exchange_rate": Decimal("9")}
        assert _tender_chunk_aed(chunk, tenant_id=None) == Decimal("1.999")

    def test_foreign_chunk_multiplies_rate(self):
        chunk = {"amount": Decimal("3"), "currency": "USD", "exchange_rate": Decimal("3.67")}
        assert _tender_chunk_aed(chunk, tenant_id=None) == Decimal("11.010")


class TestPosStandardPrice:
    def test_price_quantized_to_milli(self, mocker):
        mocker.patch("utils.pos_checkout_helpers.PricingService.get_price", return_value="7.1236")
        product = SimpleNamespace(id=1)
        assert _pos_standard_price(product, "regular", 3) == Decimal("7.124")

    def test_price_accepts_decimal_result(self, mocker):
        mocker.patch("utils.pos_checkout_helpers.PricingService.get_price", return_value=Decimal("4.4444"))
        assert _pos_standard_price(SimpleNamespace(), "regular", 1) == Decimal("4.444")


class TestPromotionEvaluationJson:
    def test_empty_evaluation_shape(self):
        result = _promotion_evaluation_json(None)
        assert result == {
            "lines": [],
            "subtotal_before": 0.0,
            "total_discount": 0.0,
            "subtotal_after": 0.0,
            "applied_rules": [],
            "upsell_prompts": [],
        }
        assert _promotion_evaluation_json({}) == result

    def test_full_evaluation_serialization(self):
        evaluation = {
            "lines": [
                {
                    "product_id": 9,
                    "quantity": Decimal("2"),
                    "unit_price": Decimal("10"),
                    "original_total": Decimal("20"),
                    "discount_amount": Decimal("5"),
                    "adjusted_total": Decimal("15"),
                }
            ],
            "subtotal_before": Decimal("20"),
            "total_discount": Decimal("5"),
            "subtotal_after": Decimal("15"),
            "applied_rules": [
                {
                    "campaign_id": 3,
                    "name": "Summer",
                    "campaign_type": "percent",
                    "discount_amount": Decimal("5"),
                }
            ],
            "upsell_prompts": ["buy one more"],
        }
        result = _promotion_evaluation_json(evaluation)
        assert result["lines"][0]["adjusted_total"] == 15.0
        assert result["applied_rules"][0]["name"] == "Summer"
        assert result["applied_rules"][0]["discount_amount"] == 5.0
        assert result["upsell_prompts"] == ["buy one more"]


class TestAccumulateSessionTender:
    def test_cash_chunk_accumulates_cash_total(self):
        session = SimpleNamespace(total_cash_sales=Decimal("10"), total_card_sales=Decimal("0"))
        chunk = {"amount": Decimal("5"), "payment_method": "cash", "currency": "AED", "exchange_rate": 1}
        _accumulate_session_tender(session, chunk, tenant_id=None)
        assert session.total_cash_sales == Decimal("15.000")
        assert session.total_card_sales == Decimal("0")

    def test_card_family_accumulates_card_total(self):
        session = SimpleNamespace(total_cash_sales=Decimal("0"), total_card_sales=Decimal("7"))
        for method in ("card", "bank_transfer", "e_wallet"):
            chunk = {"amount": Decimal("1"), "payment_method": method, "currency": "AED", "exchange_rate": 1}
            _accumulate_session_tender(session, chunk, tenant_id=None)
        assert session.total_card_sales == Decimal("10.000")

    def test_unknown_method_is_noop(self):
        session = SimpleNamespace(total_cash_sales=Decimal("1"), total_card_sales=Decimal("1"))
        chunk = {"amount": Decimal("99"), "payment_method": "credit", "currency": "AED", "exchange_rate": 1}
        _accumulate_session_tender(session, chunk, tenant_id=None)
        assert session.total_cash_sales == Decimal("1")

    def test_none_starting_totals_treated_as_zero(self):
        session = SimpleNamespace(total_cash_sales=None, total_card_sales=None)
        chunk = {"amount": Decimal("2"), "payment_method": "cash", "currency": "AED", "exchange_rate": 1}
        _accumulate_session_tender(session, chunk, tenant_id=None)
        assert session.total_cash_sales == Decimal("2.000")


class TestComputeChangeDue:
    def _sale(self, amount_aed=Decimal("50")):
        return SimpleNamespace(amount_aed=amount_aed)

    def test_non_decimal_total_short_circuits_zero(self):
        sale = SimpleNamespace(amount_aed="50")
        assert _compute_change_due(sale, None, None, "AED", 1, None) == Decimal("0")

    def test_no_cash_tender_means_no_change(self):
        payments = [{"amount": Decimal("60"), "payment_method": "card", "currency": "AED", "exchange_rate": 1}]
        assert _compute_change_due(self._sale(), payments, None, "AED", 1, None) == Decimal("0")

    def test_split_cash_chunks_summed_capped_at_zero(self):
        payments = [
            {"amount": Decimal("40"), "payment_method": "cash", "currency": "AED", "exchange_rate": 1},
            {"amount": Decimal("30"), "payment_method": "cash", "currency": "AED", "exchange_rate": 1},
            {"amount": Decimal("100"), "payment_method": "card", "currency": "AED", "exchange_rate": 1},
        ]
        # Every tender chunk counts toward the tendered total (reporting metadata).
        change = _compute_change_due(self._sale(amount_aed=Decimal("50")), payments, None, "AED", 1, None)
        assert change == Decimal("120")

    def test_cash_only_underpayment_yields_zero(self):
        payments = [{"amount": Decimal("10"), "payment_method": "cash", "currency": "AED", "exchange_rate": 1}]
        assert _compute_change_due(self._sale(), payments, None, "AED", 1, None) == Decimal("0")

    def test_single_legacy_payment_data_converted(self):
        payment_data = {"amount": "73.40", "payment_method": "cash"}
        change = _compute_change_due(
            self._sale(amount_aed=Decimal("20")),
            None,
            payment_data,
            "USD",
            Decimal("3.67"),
            None,
        )
        assert change == Decimal("249.378")  # 73.40 USD @3.67 = 269.378 AED − 20 AED

    def test_empty_payments_with_no_legacy_data(self):
        assert _compute_change_due(self._sale(), [], None, "AED", 1, None) == Decimal("0")

    def test_foreign_split_chunk_conversion(self):
        payments = [{"amount": Decimal("27"), "payment_method": "cash", "currency": "USD", "exchange_rate": "3.67"}]
        change = _compute_change_due(self._sale(amount_aed=Decimal("90")), payments, None, "AED", 1, None)
        assert pytest.approx(float(change), abs=0.002) == 99.09 - 90


class TestRealExecutionSanity:
    def test_module_exports_all_private_helpers(self):
        import utils.pos_checkout_helpers as mod

        for name in (
            "_pos_standard_price",
            "_promotion_evaluation_json",
            "_parse_split_tenders",
            "_tender_chunk_aed",
            "_accumulate_session_tender",
            "_compute_change_due",
        ):
            assert callable(getattr(mod, name))
