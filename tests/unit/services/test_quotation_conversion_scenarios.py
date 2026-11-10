"""Quotation conversion guards — expiry and stock availability (OP-02/OP-03).

Golden scenarios: an accepted quotation whose stock vanished must refuse
conversion loudly instead of creating an unfulfillable sale; an expired
quotation refuses before any sale row exists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.quotation_service import QuotationService


def _quotation(**overrides):
    q = MagicMock()
    defaults = {
        "id": 7,
        "tenant_id": 1,
        "customer_id": 5,
        "branch_id": 2,
        "warehouse_id": 3,
        "status": "accepted",
        "sale_id": None,
        "subtotal": Decimal("100"),
        "discount_amount": Decimal("0"),
        "tax_rate": Decimal("5"),
        "tax_amount": Decimal("5"),
        "total_amount": Decimal("105"),
        "currency": "AED",
        "exchange_rate": Decimal("1"),
        "base_currency": "AED",
        "amount_aed": Decimal("105"),
        "prices_include_vat": False,
        "notes": "",
        "expiry_date": datetime.now(UTC).date() + timedelta(days=30),
        "is_expired": False,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(q, key, value)
    line = MagicMock(
        product_id=50,
        quantity=Decimal("3"),
        unit_price=Decimal("40"),
        discount_percent=Decimal("0"),
        line_total=Decimal("120"),
    )
    q.lines = [line]
    return q


class TestConvertGuards:
    @staticmethod
    def _allow_warehouse(mocker):
        query = mocker.patch("utils.branching.get_accessible_warehouses_query").return_value
        query.filter_by.return_value.first.return_value = MagicMock()
        return query

    def test_insufficient_stock_refuses(self, mocker, app):
        quotation = _quotation()
        user = MagicMock(id=10)
        self._allow_warehouse(mocker)
        mocker.patch("services.stock_service.StockService.get_product_stock", return_value=Decimal("2"))
        with app.app_context(), pytest.raises(ValueError, match="المخزون غير كاف"):
            QuotationService.convert_to_sale(quotation, user)

    def test_sufficient_stock_converts(self, mocker, app):
        quotation = _quotation()
        user = MagicMock(id=10)
        self._allow_warehouse(mocker)
        mocker.patch("services.stock_service.StockService.get_product_stock", return_value=Decimal("10"))
        mocker.patch("services.quotation_service.generate_number", return_value="SALE-NEW")
        mocker.patch("services.quotation_service.db.session.add")
        mocker.patch("services.quotation_service.db.session.flush")
        with app.app_context():
            sale = QuotationService.convert_to_sale(quotation, user)
        assert quotation.status == "converted_to_sale"
        assert sale is not None

    def test_expired_refuses(self, mocker, app):
        # The real model's is_expired property is False once the quote is
        # accepted, even when its expiry date is in the past.
        quotation = _quotation(expiry_date=datetime.now(UTC).date() - timedelta(days=1), is_expired=False)
        user = MagicMock(id=10)
        mocker.patch("services.stock_service.StockService.get_product_stock", return_value=Decimal("10"))
        with app.app_context(), pytest.raises(ValueError, match="منتهي الصلاحية"):
            QuotationService.convert_to_sale(quotation, user)

    def test_duplicate_product_lines_are_summed(self, mocker, app):
        quotation = _quotation()
        quotation.lines.append(MagicMock(product_id=50, quantity=Decimal("2")))
        self._allow_warehouse(mocker)
        mocker.patch("services.stock_service.StockService.get_product_stock", return_value=Decimal("4"))
        with app.app_context(), pytest.raises(ValueError, match="المخزون غير كاف"):
            QuotationService.convert_to_sale(quotation, MagicMock(id=10))

    def test_inaccessible_warehouse_refuses_before_stock_lookup(self, mocker, app):
        quotation = _quotation()
        query = mocker.patch("utils.branching.get_accessible_warehouses_query").return_value
        query.filter_by.return_value.first.return_value = None
        stock = mocker.patch("services.stock_service.StockService.get_product_stock")
        with app.app_context(), pytest.raises(ValueError, match="المستودع المحدد غير متاح"):
            QuotationService.convert_to_sale(quotation, MagicMock(id=10))
        query.filter_by.assert_called_once_with(id=3, tenant_id=1)
        stock.assert_not_called()

    def test_accept_expired_refuses(self, app):
        quotation = _quotation(status="sent", is_expired=True)
        with app.app_context(), pytest.raises(ValueError, match="منتهي الصلاحية"):
            QuotationService.accept_quotation(quotation)

    def test_double_conversion_refuses(self, app):
        quotation = _quotation(sale_id=99)
        user = MagicMock(id=10)
        with app.app_context(), pytest.raises(ValueError, match="تم تحويل"):
            QuotationService.convert_to_sale(quotation, user)
