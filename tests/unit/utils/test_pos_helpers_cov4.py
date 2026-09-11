"""Cov4: pos_helpers pure — decimals, scale barcodes, merge lines, fast cash, cfd/tickets."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils.pos_helpers as ph


def test_safe_decimal():
    assert ph.safe_decimal(None) == Decimal("0")  # 25-30
    assert ph.safe_decimal("bad!!") == Decimal("0")
    assert ph.safe_decimal("1.5") == Decimal("1.5")
    assert ph.safe_decimal("x", default=Decimal("9")) == Decimal("9")


def _valid_scale():
    body = "200000100500"
    digits = [int(d) for d in body]
    chk = (10 - (sum(digits[::2]) + 3 * sum(digits[1::2])) % 10) % 10
    return body + str(chk)


def test_scale_barcode():
    assert ph.parse_scale_barcode(None) is None  # 47-49
    assert ph.parse_scale_barcode("123") is None
    assert ph.parse_scale_barcode("9900001005007") is None  # wrong prefix
    code = _valid_scale()
    out = ph.parse_scale_barcode(code)  # 50-59
    assert out["item_code"] == code[2:7]
    bad = code[:-1] + ("0" if code[-1] != "0" else "1")
    assert ph.parse_scale_barcode(bad) is None  # 52-53 checksum


def test_payment_amount_branches():
    assert ph.payment_amount_base(SimpleNamespace(amount="5")) == Decimal("5.000")  # 71-72 legacy
    with patch("utils.pos_helpers.convert_and_quantize_aed", return_value=Decimal("7.000")):
        p = SimpleNamespace(amount="5", currency="USD", exchange_rate="3")
        assert ph.payment_amount_base(p, tenant_id=1) == Decimal("7.000")  # 73-76
    with patch("utils.pos_helpers.convert_and_quantize_aed", return_value=Decimal("5.000")):
        p2 = SimpleNamespace(amount="5", currency="USD", exchange_rate="0")
        assert ph.payment_amount_base(p2) == Decimal("5.000")  # 74-75 zero rate


def test_warehouse_ids_and_merge():
    assert ph._warehouse_ids_for_stock(9) == [9]  # 133-136
    with patch("utils.pos_helpers.get_accessible_warehouse_ids", return_value=[1, 2]):
        assert ph._warehouse_ids_for_stock(None) == [1, 2]
    with pytest.raises(ValueError):  # 273-275 non-dict
        ph.merge_checkout_lines(["x"])
    with pytest.raises(ValueError):  # bad qty
        ph.merge_checkout_lines([{"product_id": 1, "quantity": "bad"}])
    with pytest.raises(ValueError):  # zero qty
        ph.merge_checkout_lines([{"product_id": 1, "quantity": 0}])
    with pytest.raises(ValueError):  # bad discount
        ph.merge_checkout_lines([{"product_id": 1, "quantity": 1, "discount_percent": 150}])
    out = ph.merge_checkout_lines(
        [
            {"product_id": 1, "quantity": 2, "discount_percent": 5, "unit_price": "10"},
            {"product_id": 1, "quantity": 1, "discount_percent": 0, "unit_price": "12"},
        ]
    )  # 289-302 merge
    assert out[0]["quantity"] == Decimal("3")
    assert out[0]["unit_price"] == Decimal("12")


def test_fast_cash():
    with pytest.raises(ValueError):  # 523-524
        ph.compute_fast_cash_options(-5)
    opts = ph.compute_fast_cash_options(100, "AED")  # happy
    assert opts[0]["is_exact"] is True
    opts2 = ph.compute_fast_cash_options(7, "ZZZ-UNKNOWN")  # fallback currency 526-527
    assert opts2[0]["amount"] == Decimal("7.000")
    opts3 = ph.compute_fast_cash_options(10, "AED", max_options=2)  # 544-546 cap
    assert opts3[0]["is_exact"] is True and len(opts3) == 2


def test_cfd_and_tickets():
    line = SimpleNamespace(
        quantity=2,
        unit_price=10,
        discount_percent=0,
        line_total=Decimal("20"),
        product=SimpleNamespace(name="P", name_ar="ب"),
        product_id=1,
    )
    sale = SimpleNamespace(
        lines=[line],
        tax_rate=Decimal("5"),
        taxable_amount=Decimal("20"),
        tax_amount=Decimal("1"),
        total_amount=Decimal("21"),
        paid_amount=Decimal("30"),
        subtotal=Decimal("20"),
        discount_amount=Decimal("0"),
        promotion_discount_amount=Decimal("0"),
        sale_number="S-1",
    )
    payload = ph.build_cfd_order_payload(sale)  # standard bucket 587-589
    assert payload["tax_breakdown"]["standard"]["tax"] == 1.0
    sale0 = SimpleNamespace(
        lines=[],
        tax_rate=Decimal("0"),
        taxable_amount=Decimal("20"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("20"),
        paid_amount=Decimal("10"),
        subtotal=Decimal("20"),
        discount_amount=Decimal("0"),
        promotion_discount_amount=Decimal("0"),
        sale_number="S-2",
    )
    p0 = ph.build_cfd_order_payload(sale0)  # zero-rated 590-592
    assert p0["tax_breakdown"]["zero_rated"]["base"] == 20.0
    printer = SimpleNamespace(role="customer", name="P1", connection_type="usb", agent_printer_payload=lambda: {"x": 1})
    sale3 = SimpleNamespace(lines=[line], total_amount=Decimal("20"), sale_number="S-3")
    tickets = ph.build_print_tickets(sale3, [printer])  # 663-695 customer
    assert tickets[0]["role"] == "customer"
    kitchen = SimpleNamespace(
        role="kitchen",
        name="K",
        connection_type="net",
        agent_printer_payload=lambda: {},
        covers_category=lambda c: False,
    )
    assert ph.build_print_tickets(sale3, [kitchen]) == []  # 684-685 skip
    kitchen2 = SimpleNamespace(
        role="kitchen",
        name="K",
        connection_type="net",
        agent_printer_payload=lambda: {},
        covers_category=lambda c: True,
    )
    line2 = SimpleNamespace(quantity=1, line_total=Decimal("5"), product_id=9, product=None)
    sale4 = SimpleNamespace(lines=[line2], total_amount=Decimal("5"), sale_number="S-4")
    assert len(ph.build_print_tickets(sale4, [kitchen2])) == 1  # product None name 640-644
    assert ph.build_print_tickets(sale4, None) == []
