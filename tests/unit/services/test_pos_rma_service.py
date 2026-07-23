"""POS Phase 4 — PosRmaService: receipt lookup, promo allocation, stock
breakdown, and cash-refund orchestration. Mocked at the DB boundary per
tests/unit/services conventions (same style as test_return_service_assurance).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.pos_rma_service import PosRmaService, _promo_allocations


def _user(uid=42):
    user = MagicMock()
    user.id = uid
    user.is_authenticated = True
    user.is_owner = False
    return user


def _scoped_query(mocker, first_result):
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = first_result
    mocker.patch("services.pos_rma_service.tenant_query", return_value=query)
    mocker.patch("services.pos_rma_service.branch_scope_id_for", return_value=None)
    return query


def _sale(sale_id=55, promo=None):
    sale = MagicMock()
    sale.id = sale_id
    sale.tenant_id = 1
    sale.branch_id = 2
    sale.sale_number = "S-1001"
    sale.sale_date = None
    sale.status = "confirmed"
    sale.payment_status = "paid"
    sale.customer_id = 5
    sale.customer = MagicMock(name="Customer")
    sale.customer.name = "Acme"
    sale.currency = "USD"
    sale.exchange_rate = Decimal("3.0")
    sale.subtotal = Decimal("100")
    sale.discount_amount = Decimal("0")
    sale.shipping_cost = Decimal("0")
    sale.tax_rate = Decimal("0")
    sale.tax_amount = Decimal("0")
    sale.total_amount = Decimal("90")
    if promo is not None:
        sale.promotion_discount_amount = promo
    return sale


def _line(line_id, product_id, qty, total):
    line = MagicMock()
    line.id = line_id
    line.product_id = product_id
    line.quantity = Decimal(str(qty))
    line.unit_price = Decimal(str(total)) / Decimal(str(qty))
    line.discount_percent = Decimal("0")
    line.line_total = Decimal(str(total))
    line.product = MagicMock()
    line.product.name = f"P{product_id}"
    line.product.sku = f"SKU{product_id}"
    line.product.barcode = f"BC{product_id}"
    return line


def _stub_returned_map(mocker, rows):
    session = mocker.patch("services.pos_rma_service.db.session")
    chain = MagicMock()
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.group_by.return_value = chain
    chain.all.return_value = rows
    session.query.return_value = chain
    return session


class TestPromoAllocations:
    def test_proportional_shares_sum_exactly(self):
        sale = MagicMock()
        sale.promotion_discount_amount = Decimal("10")
        sale.subtotal = Decimal("100")
        sale.lines = [_line(1, 11, 1, 33.333), _line(2, 12, 1, 33.333), _line(3, 13, 1, 33.334)]
        shares = _promo_allocations(sale)
        assert sum(shares.values()) == Decimal("10.000")
        # Largest line absorbs the rounding residual.
        assert shares[3] == Decimal("3.334")

    def test_no_promo_returns_empty(self):
        sale = MagicMock()
        sale.subtotal = Decimal("100")
        sale.lines = [_line(1, 11, 1, 100)]
        assert _promo_allocations(sale) == {}


class TestLookupReceipt:
    def test_found_with_returned_netting(self, mocker):
        sale = _sale(promo=Decimal("10"))
        sale.lines = [_line(201, 11, 5, 60), _line(202, 12, 2, 40)]
        _scoped_query(mocker, sale)
        _stub_returned_map(mocker, [(201, Decimal("2"))])

        receipt = PosRmaService.lookup_receipt(_user(), "S-1001")

        assert receipt["sale_id"] == 55
        assert receipt["currency"] == "USD"
        assert receipt["exchange_rate"] == 3.0
        first, second = receipt["lines"]
        assert first["quantity_returned"] == 2.0
        assert first["quantity_returnable"] == 3.0
        assert second["quantity_returned"] == 0.0
        # Promo allocation: 60% / 40% of the recorded 10.
        assert first["promo_discount_share"] == 6.0
        assert second["promo_discount_share"] == 4.0

    def test_not_found_returns_none(self, mocker):
        _scoped_query(mocker, None)
        _stub_returned_map(mocker, [])
        assert PosRmaService.lookup_receipt(_user(), "NOPE") is None

    def test_empty_number_raises(self):
        with pytest.raises(ValueError):
            PosRmaService.lookup_receipt(_user(), "   ")

    def test_branch_scope_filter_applied(self, mocker):
        query = _scoped_query(mocker, None)
        mocker.patch("services.pos_rma_service.branch_scope_id_for", return_value=9)
        _stub_returned_map(mocker, [])
        PosRmaService.lookup_receipt(_user(), "S-1001")
        assert query.filter.call_count == 2  # sale_number + branch scope


class TestStockBreakdown:
    def test_per_warehouse_breakdown(self, mocker):
        product = MagicMock()
        product.id = 11
        product.name = "Widget"
        product.sku = "SKU11"
        product.barcode = "BC11"
        _scoped_query(mocker, product)

        wh_a = MagicMock(id=1, name="Main WH", code="M", branch_id=2, is_active=True)
        wh_a.branch = MagicMock(name="Branch A")
        wh_b = MagicMock(id=2, name="Branch WH", code="B", branch_id=3, is_active=True)
        wh_b.branch = MagicMock(name="Branch B")
        mocker.patch("services.pos_rma_service.get_accessible_warehouses", return_value=[wh_a, wh_b])
        stock_mock = mocker.patch(
            "services.pos_rma_service.get_warehouse_stock_map",
            return_value={(11, 1): Decimal("7"), (11, 2): Decimal("3")},
        )

        result = PosRmaService.stock_breakdown(_user(), product_id=11)

        assert result["total_on_hand"] == 10.0
        assert [r["on_hand"] for r in result["warehouses"]] == [7.0, 3.0]
        assert result["warehouses"][1]["branch_id"] == 3
        stock_mock.assert_called_once_with(product_ids=[11], warehouse_ids=[1, 2])

    def test_not_found_returns_none(self, mocker):
        _scoped_query(mocker, None)
        mocker.patch("services.pos_rma_service.get_accessible_warehouses", return_value=[])
        mocker.patch("services.pos_rma_service.get_warehouse_stock_map", return_value={})
        assert PosRmaService.stock_breakdown(_user(), product_id=999) is None


class TestCreatePosReturn:
    def _product_return(self):
        product_return = MagicMock()
        product_return.id = 88
        product_return.return_number = "R-100"
        product_return.currency = "USD"
        product_return.exchange_rate = Decimal("3.0")
        product_return.refund_amount = Decimal("100")
        product_return.amount_aed = Decimal("300")
        product_return.sale = _sale()
        return product_return

    def test_credit_refund_is_default_and_creates_no_payment(self, mocker):
        product_return = self._product_return()
        create_mock = mocker.patch(
            "services.pos_rma_service.ReturnService.create_return",
            return_value=product_return,
        )
        mocker.patch("services.pos_rma_service.db.session")
        payment_spy = mocker.patch("services.pos_rma_service.Payment")

        result, payment = PosRmaService.create_pos_return(
            user=_user(),
            session=MagicMock(),
            shift=None,
            sale_id=55,
            return_lines=[{"sale_line_id": 201, "quantity": 1}],
            refund_method="credit",
        )

        assert result is product_return
        assert payment is None
        payment_spy.assert_not_called()
        create_mock.assert_called_once()

    def test_invalid_refund_method_raises(self):
        with pytest.raises(ValueError, match="credit"):
            PosRmaService.create_pos_return(
                user=_user(),
                session=MagicMock(),
                shift=None,
                sale_id=55,
                return_lines=[],
                refund_method="crypto",
            )

    def test_cash_refund_gl_balanced_and_session_totals(self, mocker):
        product_return = self._product_return()
        mocker.patch(
            "services.pos_rma_service.ReturnService.create_return",
            return_value=product_return,
        )
        mocker.patch("services.pos_rma_service.generate_number", return_value="PAY-500")
        mocker.patch("services.pos_rma_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.pos_rma_service.GLService.get_customer_credit_account",
            return_value="1130",
        )
        mocker.patch(
            "services.pos_rma_service.GLService.get_customer_credit_concept",
            return_value="AR",
        )
        mocker.patch(
            "services.pos_rma_service.resolve_pos_cash_account_code",
            return_value="1111",
        )
        post_mock = mocker.patch("services.pos_rma_service.post_or_fail")
        mocker.patch("services.pos_rma_service.db.session")

        session = MagicMock()
        session.branch_id = 2
        session.total_cash_refunds = Decimal("50")
        shift = MagicMock()
        shift.total_cash_refunds = Decimal("20")

        _, payment = PosRmaService.create_pos_return(
            user=_user(),
            session=session,
            shift=shift,
            sale_id=55,
            return_lines=[{"sale_line_id": 201, "quantity": 1}],
            refund_method="cash",
        )

        assert payment is not None
        assert payment.payment_type == "refund"
        assert payment.direction == "outgoing"
        # NOT linked to the sale: recalculate_payment_status counts every
        # confirmed payment on the sale as money received.
        assert payment.sale_id is None
        assert Decimal(str(payment.amount)) == Decimal("100.000")
        assert Decimal(str(payment.exchange_rate)) == Decimal("3.0")

        # GL: Dr customer credit 100 / Cr cash 100 at the ORIGINAL rate.
        gl_kwargs = post_mock.call_args.kwargs
        legs = post_mock.call_args.args[0]
        debit_total = sum(Decimal(str(l.get("debit", 0))) for l in legs)
        credit_total = sum(Decimal(str(l.get("credit", 0))) for l in legs)
        assert debit_total == credit_total == Decimal("100.000")
        assert legs[0]["account"] == "1130"
        assert legs[1]["account"] == "1111"
        assert Decimal(str(gl_kwargs["exchange_rate"])) == Decimal("3.0")

        # Drawer totals: expected = opening + cash − change − refunds + in − out.
        assert session.total_cash_refunds == Decimal("350")
        assert shift.total_cash_refunds == Decimal("320")

        # The return's customer credit is consumed by the cash hand-out.
        product_return.sale.customer.adjust_balance.assert_called_once_with(Decimal("-300"))
