"""Gap coverage for models/product_return.py — totals, aliases, reprs."""

from __future__ import annotations

from decimal import Decimal

from models.product_return import ProductReturn, ProductReturnLine


def _return(**kwargs):
    params = {
        "tenant_id": 1,
        "return_number": "RET-COV3",
        "sale_id": 1,
        "customer_id": 1,
        "total_amount": Decimal("0"),
        "amount_aed": Decimal("0"),
    }
    params.update(kwargs)
    return ProductReturn(**params)


def _line(total):
    return ProductReturnLine(
        tenant_id=1,
        return_id=1,
        product_id=1,
        quantity=Decimal("1"),
        unit_price=Decimal(str(total)),
        line_total=Decimal(str(total)),
    )


class TestCalculateTotals:
    def test_sums_lines_and_uses_rate(self):
        ret = _return(exchange_rate=Decimal("2"))
        ret.lines = [_line("30.5"), _line("10")]
        ret.refund_amount = Decimal("40.5")
        ret.calculate_totals()
        assert ret.total_amount == Decimal("40.5")
        assert ret.amount_aed == Decimal("81.000")

    def test_none_exchange_defaults_to_one(self):
        ret = _return(exchange_rate=None)
        ret.lines = [_line("25")]
        ret.refund_amount = Decimal("25")
        ret.calculate_totals()
        assert ret.amount_aed == Decimal("25.000")

    def test_refund_falls_back_to_total(self):
        ret = _return(exchange_rate=Decimal("1"))
        ret.lines = [_line("12.345")]
        ret.refund_amount = Decimal("0")
        ret.calculate_totals()
        assert ret.total_amount == Decimal("12.345")
        assert ret.amount_aed == Decimal("12.345")

    def test_empty_lines(self):
        ret = _return(exchange_rate=Decimal("3"))
        ret.lines = []
        ret.refund_amount = None
        ret.total_amount = None
        ret.calculate_totals()
        assert ret.total_amount == Decimal("0")
        assert ret.amount_aed == Decimal("0.000")


class TestAliases:
    def test_base_amount_getter_setter(self):
        ret = _return(amount_aed=Decimal("9.5"))
        assert ret.base_amount == Decimal("9.5")
        ret.base_amount = Decimal("3.25")
        assert ret.amount_aed == Decimal("3.25")

    def test_base_currency_display(self):
        assert _return(base_currency="AED").base_currency_display == "AED"

    def test_reprs(self):
        assert "RET-COV3" in repr(_return())
        line = _line("5")
        assert "x 1" in repr(line)
