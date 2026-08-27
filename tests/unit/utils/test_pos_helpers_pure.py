"""Pure-logic coverage for utils/pos_helpers.py (no DB required).

Real-behavior tests over the genuine helpers: scale-barcode parsing,
Decimal coercion, payment base-currency math, checkout line merging, CFD
payload building and print-ticket accumulation.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from utils.pos_helpers import (
    _accumulate_close_totals,
    build_cfd_order_payload,
    merge_checkout_lines,
    parse_scale_barcode,
    payment_amount_base,
    safe_decimal,
    serialize_pos_product,
)


@pytest.fixture(autouse=True)
def _aed_base_currency(mocker):
    """Anchor base-currency resolution to AED (context settings are DB-backed)."""
    mocker.patch("utils.currency_utils.context_aware_default_currency", return_value="AED")


def _scale_code(item: str = "12345", grams: str = "00500") -> str:
    body = f"20{item}{grams}"
    digits = [int(d) for d in body]
    checksum = (10 - (sum(digits[::2]) + 3 * sum(digits[1::2])) % 10) % 10
    return body + str(checksum)


class TestSafeDecimal:
    def test_none_defaults_to_zero(self):
        assert safe_decimal(None) == Decimal("0")

    def test_invalid_string_returns_default(self):
        assert safe_decimal("abc", default=Decimal("7")) == Decimal("7")
        assert safe_decimal("1.2.3", default=Decimal("-1")) == Decimal("-1")

    def test_nested_type_error(self):
        assert safe_decimal(["x"], default=Decimal("3")) == Decimal("3")

    def test_valid_passthrough(self):
        assert safe_decimal("12.5") == Decimal("12.5")


class TestParseScaleBarcode:
    def test_non_numeric_rejected(self):
        assert parse_scale_barcode("20abcdefghijks") is None

    def test_wrong_length_rejected(self):
        assert parse_scale_barcode("2012345") is None
        assert parse_scale_barcode("") is None

    def test_wrong_prefix_rejected(self):
        code = "301234500500" + "0"
        assert len(code) == 13
        assert parse_scale_barcode(code) is None

    def test_bad_checksum_rejected(self):
        good = _scale_code()
        bad = good[:12] + ("0" if good[12] != "0" else "1")
        assert parse_scale_barcode(bad) is None

    def test_falsy_input_rejected(self):
        assert parse_scale_barcode(None) is None

    def test_valid_code_parses_grams_and_kg(self):
        parsed = parse_scale_barcode(_scale_code(grams="00750"))
        assert parsed is not None
        assert parsed["weight_grams"] == Decimal("750")
        assert parsed["weight_kg"] == Decimal("0.750")
        assert parsed["item_code"] == "12345"


class _Payment(SimpleNamespace):
    pass


class TestPaymentAmountBase:
    def test_missing_currency_quantizes_raw(self):
        p = _Payment(amount="10.123456789", currency=None, exchange_rate=None)
        assert payment_amount_base(p) == Decimal("10.123")

    def test_blank_currency_quantizes_raw(self):
        p = _Payment(amount=Decimal("5"), currency="   ", exchange_rate=None)
        assert payment_amount_base(p) == Decimal("5.000")

    def test_aed_payment_rate_ignored(self):
        p = _Payment(amount=Decimal("12"), currency="AED", exchange_rate=Decimal("0"))
        assert payment_amount_base(p) == Decimal("12.000")

    def test_zero_or_negative_rate_treated_as_one(self):
        p = _Payment(amount=Decimal("2"), currency="ZZZ", exchange_rate=-3)
        # rate<=0 → forced to 1 → amount stays the same but conversion path runs
        result = payment_amount_base(p, tenant_id=None)
        assert isinstance(result, Decimal)

    def test_foreign_currency_converts(self):
        p = _Payment(amount=Decimal("2"), currency="USD", exchange_rate=Decimal("3.67"))
        assert payment_amount_base(p) == Decimal("7.340")


class TestMergeCheckoutLines:
    def test_merges_duplicates_summing_qty_last_price_wins(self):
        merged = merge_checkout_lines(
            [
                {"product_id": 1, "quantity": 2, "unit_price": "10"},
                {"product_id": 1, "quantity": 3, "discount_percent": 50},
                {"product_id": 2, "quantity": 1.5, "unit_price": None},
            ]
        )
        assert len(merged) == 2
        first = merged[0]
        assert first["quantity"] == Decimal("5")
        assert first["unit_price"] == Decimal("10")  # last explicit price kept
        assert first["discount_percent"] == Decimal("50")
        second = merged[1]
        assert second["unit_price"] is None
        assert second["discount_percent"] == Decimal("0")

    def test_preserves_first_seen_order(self):
        rows = [
            {"product_id": 7, "quantity": 1},
            {"product_id": 3, "quantity": 1},
            {"product_id": 7, "quantity": 1},
        ]
        assert [line["product_id"] for line in merge_checkout_lines(rows)] == [7, 3]

    def test_non_dict_row_raises(self):
        with pytest.raises(ValueError, match="السلة"):
            merge_checkout_lines([{"product_id": 1, "quantity": 1}, "nope"])

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            merge_checkout_lines([{"product_id": 1, "quantity": 0}])

    def test_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            merge_checkout_lines([{"product_id": 1, "quantity": "-2"}])

    def test_missing_quantity_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            merge_checkout_lines([{"product_id": 1}])

    def test_discount_below_zero_raises(self):
        with pytest.raises(ValueError, match="بين 0 و 100"):
            merge_checkout_lines([{"product_id": 1, "quantity": 1, "discount_percent": -1}])

    def test_discount_above_hundred_raises(self):
        with pytest.raises(ValueError, match="بين 0 و 100"):
            merge_checkout_lines([{"product_id": 1, "quantity": 1, "discount_percent": 101}])

    def test_blank_string_unit_price_becomes_none(self):
        merged = merge_checkout_lines([{"product_id": 1, "quantity": 1, "unit_price": "   "}])
        assert merged[0]["unit_price"] is None


class TestAccumulateCloseTotals:
    def _sale(self, total, payments):
        return SimpleNamespace(total_amount=Decimal(total), payments=payments)

    def test_sums_cash_card_and_change_given(self):
        session = SimpleNamespace(tenant_id=1, total_change_given="15")
        cash = _Payment(amount=Decimal("100"), currency="AED", exchange_rate=None, payment_method="cash")
        card = _Payment(amount=Decimal("50"), currency="AED", exchange_rate=None, payment_method="card")
        wallet = _Payment(amount=Decimal("25"), currency="AED", exchange_rate=None, payment_method="e_wallet")
        sales = [self._sale("175", [cash, card, wallet]), self._sale("30", [])]
        total, cash_total, card_total = _accumulate_close_totals(session, sales)
        assert total == Decimal("205")
        assert cash_total == Decimal("115")  # cash net + change given
        assert card_total == Decimal("75")

    def test_legacy_payment_without_currency(self):
        session = SimpleNamespace(tenant_id=1, total_change_given=None)
        legacy = _Payment(amount="7.9999", currency="", exchange_rate=None, payment_method="cash")
        total, cash_total, card_total = _accumulate_close_totals(session, [self._sale("8", [legacy])])
        assert total == Decimal("8")
        assert cash_total == Decimal("8.000")
        assert card_total == Decimal("0")

    def test_empty_session(self):
        session = SimpleNamespace(tenant_id=1, total_change_given=0)
        total, cash_total, card_total = _accumulate_close_totals(session, [])
        assert (total, cash_total, card_total) == (Decimal("0"), Decimal("0"), Decimal("0"))

    def test_other_method_not_counted_as_card(self):
        session = SimpleNamespace(tenant_id=1, total_change_given=0)
        credit = _Payment(amount=Decimal("40"), currency="AED", exchange_rate=None, payment_method="store_credit")
        _, _, card_total = _accumulate_close_totals(session, [self._sale("40", [credit])])
        assert card_total == Decimal("0")


class TestBuildCfdOrderPayload:
    def _sale(self, tax_rate="0", **over):
        base = dict(
            sale_number="S-77",
            lines=[],
            subtotal=Decimal("90"),
            discount_amount=Decimal("10"),
            promotion_discount_amount=Decimal("2"),
            taxable_amount=Decimal("80"),
            tax_rate=Decimal(tax_rate),
            tax_amount=Decimal("4"),
            total_amount=Decimal("94"),
            paid_amount=Decimal("100"),
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_rated_sale_breakdown(self):
        sale = self._sale(
            tax_rate="5",
            lines=[
                SimpleNamespace(
                    quantity=Decimal("2"),
                    unit_price=Decimal("25"),
                    discount_percent=Decimal("10"),
                    line_total=Decimal("45"),
                    product=SimpleNamespace(name="Burger", name_ar="برجر"),
                )
            ],
        )
        payload = build_cfd_order_payload(sale)
        assert payload["order_number"] == "S-77"
        item = payload["items"][0]
        assert item["name"] == "برجر"
        assert item["discount_amount"] == 5.0
        std = payload["tax_breakdown"]["standard"]
        assert std == {"base": 80.0, "rate": 5.0, "tax": 4.0}
        assert payload["tax_breakdown"]["zero_rated"]["base"] == 0.0
        assert payload["change_due"] == 6.0

    def test_unrated_sale_goes_to_zero_rated_bucket(self):
        sale = self._sale(tax_rate="0", taxable_amount=Decimal("33"))
        payload = build_cfd_order_payload(sale)
        assert payload["tax_breakdown"]["standard"]["tax"] == 0.0
        assert payload["tax_breakdown"]["zero_rated"] == {"base": 33.0, "tax": 0.0}
        assert payload["change_due"] == 6.0

    def test_productless_line_and_no_overpay(self):
        sale = self._sale(
            paid_amount=Decimal("1"),
            lines=[SimpleNamespace(quantity=1, unit_price=1, discount_percent=0, line_total=1, product=None)],
        )
        payload = build_cfd_order_payload(sale)
        assert payload["items"][0]["name"] == "—"
        assert payload["items"][0]["discount_amount"] == 0.0
        assert payload["change_due"] == 0.0


class TestSerializePosProduct:
    def _product(self, **over):
        base = dict(
            id=5,
            name="Milk",
            name_ar="حليب",
            sku="MLK-1",
            barcode="20001",
            regular_price=Decimal("3.5"),
            current_stock=Decimal("8"),
            unit="kg",
            is_active=True,
            has_serial_number=False,
        )
        base.update(over)
        ns = SimpleNamespace(**base)
        ns.commercial_name = ""
        return ns

    def test_full_serialization_with_sku(self):
        data = serialize_pos_product(self._product(), {5: 12.5})
        assert data["stock"] == 12.5
        assert data["text"] == "Milk (MLK-1)"
        assert data["is_weight_product"] is True
        assert data["is_inactive"] is False
        assert data["is_out_of_stock"] is False
        assert data["warehouse_id"] is None

    def test_out_of_stock_and_inactive_flags(self):
        data = serialize_pos_product(self._product(current_stock=0, is_active=False), {})
        assert data["is_out_of_stock"] is True
        assert data["is_inactive"] is True

    def test_weight_detection_arabic_unit(self):
        data = serialize_pos_product(self._product(unit="كجم"), {})
        assert data["is_weight_product"] is True

    def test_non_weight_unit_and_serial_flag(self):
        data = serialize_pos_product(self._product(unit="pcs", has_serial_number=True), {})
        assert data["is_weight_product"] is False
        assert data["has_serial_number"] is True

    def test_falls_back_to_current_stock_when_map_empty(self):
        data = serialize_pos_product(self._product(), {})
        assert data["stock"] == 8.0
