"""Coverage-4 for services.pos_rma_service — except/else/fallback arcs."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.pos_rma_service import PosRmaService, _money, _promo_allocations


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestMoneyAndPromo:
    def test_money_none_and_zero(self):
        assert _money(None) == Decimal("0.000")
        assert _money(0) == Decimal("0.000")

    def test_promo_no_discount_returns_empty(self):
        sale = SimpleNamespace(promotion_discount_amount=None, subtotal=100, lines=[])
        assert _promo_allocations(sale) == {}

    def test_promo_zero_subtotal_returns_empty(self):
        sale = SimpleNamespace(promotion_discount_amount=Decimal("10"), subtotal=0, lines=[])
        assert _promo_allocations(sale) == {}

    def test_promo_residual_goes_to_largest_line(self):
        l1 = SimpleNamespace(id=1, line_total=Decimal("33.33"))
        l2 = SimpleNamespace(id=2, line_total=Decimal("66.67"))
        sale = SimpleNamespace(
            promotion_discount_amount=Decimal("10"), subtotal=Decimal("100"), lines=[l1, l2]
        )
        shares = _promo_allocations(sale)
        assert sum(shares.values(), Decimal("0")) == Decimal("10.000")


class TestResolveSaleId:
    def test_garbage_sale_id_returns_none(self, mocker):

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = MagicMock(id=9)
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        # unparseable id + no sale_number -> None (except TypeError/ValueError arc)
        out = PosRmaService.resolve_sale_id(MagicMock(), sale_id="not-an-int")
        assert out is None

    def test_sale_number_blank_returns_none(self, mocker):
        mocker.patch("services.pos_rma_service.tenant_query")
        assert PosRmaService.resolve_sale_id(MagicMock(), sale_number="   ") is None

    def test_sale_number_with_branch_scope(self, mocker):

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = MagicMock(id=42)
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        mocker.patch("services.pos_rma_service.branch_scope_id_for", return_value=3)
        assert PosRmaService.resolve_sale_id(MagicMock(), sale_number=" R-1 ") == 42

    def test_resolve_by_id_hit(self, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = MagicMock(id=7)
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        assert PosRmaService.resolve_sale_id(MagicMock(), sale_id="7") == 7


class TestLookupReceipt:
    def test_blank_number_raises(self):
        with pytest.raises(ValueError):
            PosRmaService.lookup_receipt(MagicMock(), "   ")

    def test_missing_receipt_returns_none(self, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        mocker.patch("services.pos_rma_service.branch_scope_id_for", return_value=None)
        assert PosRmaService.lookup_receipt(MagicMock(), "NOPE-1") is None

    def test_returnable_clamped_at_zero(self, mocker):
        from datetime import datetime

        line = SimpleNamespace(
            id=11, product_id=5, quantity=Decimal("2"), unit_price=Decimal("10"),
            discount_percent=Decimal("0"), line_total=Decimal("20"),
            product=SimpleNamespace(name="P", sku="S", barcode="B"),
        )
        sale = SimpleNamespace(
            id=1, tenant_id=9, sale_number="R-9", sale_date=datetime.now(), status="confirmed",
            payment_status="paid", customer_id=None, customer=None, currency="AED",
            exchange_rate=Decimal("1"), subtotal=Decimal("20"), discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"), tax_rate=Decimal("0"), tax_amount=Decimal("0"),
            total_amount=Decimal("20"), lines=[line], promotion_discount_amount=None,
        )
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = sale
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        mocker.patch("services.pos_rma_service.branch_scope_id_for", return_value=None)
        mocker.patch("services.pos_rma_service._returned_quantities", return_value={11: Decimal("5")})
        out = PosRmaService.lookup_receipt(MagicMock(), "R-9")
        assert out["lines"][0]["quantity_returnable"] == 0.0


class TestStockBreakdownAndGuards:
    def test_no_identifier_returns_none(self):
        assert PosRmaService.stock_breakdown(MagicMock()) is None

    def test_product_not_found_returns_none(self, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mocker.patch("services.pos_rma_service.tenant_query", return_value=mock_q)
        assert PosRmaService.stock_breakdown(MagicMock(), product_id=999) is None

    def test_cash_refund_zero_raises(self):
        pr = SimpleNamespace(refund_amount=Decimal("0"))
        with pytest.raises(ValueError):
            PosRmaService._create_cash_refund_payment(
                product_return=pr, sale=MagicMock(), session=MagicMock(), user=MagicMock()
            )

    def test_create_pos_return_bad_method(self):
        with pytest.raises(ValueError):
            PosRmaService.create_pos_return(
                user=MagicMock(), session=MagicMock(), shift=None,
                sale_id=1, return_lines=[], refund_method="bitcoin",
            )

    def test_permission_checks(self):
        assert PosRmaService.user_can_return_beyond_own_sales(SimpleNamespace(is_owner=True)) is True
        assert PosRmaService.user_can_return_beyond_own_sales(SimpleNamespace()) is False
        checker = SimpleNamespace(is_owner=False, has_permission=lambda p: True)
        assert PosRmaService.user_can_return_beyond_own_sales(checker) is True
