"""Cov5: store_order_service — zero-total award, missing loyalty row, couponless cancel."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def test_award_loyalty_zero_total_skips_earn(mocker, online_sale):
    from services.store_order_service import StoreOrderService

    earn = mocker.patch("services.store_service.StoreService.earn_loyalty_points")
    txn_q = mocker.patch("models.shop_loyalty.ShopLoyaltyTransaction.query")
    txn_q.filter_by.return_value.first.return_value = None
    acct_q = mocker.patch("models.shop_customer_account.ShopCustomerAccount.query")
    acct_q.filter_by.return_value.first.return_value = MagicMock(id=1)
    online_sale.customer_id = 1
    online_sale.total_amount = Decimal("0")
    StoreOrderService._award_loyalty_points(online_sale)
    earn.assert_not_called()


def test_reverse_loyalty_without_loyalty_row(mocker, online_sale):
    from services.store_order_service import StoreOrderService

    txn = MagicMock(points=25)
    mocker.patch("models.shop_loyalty.ShopLoyaltyTransaction.query").filter_by.return_value.first.return_value = txn
    mocker.patch("models.shop_loyalty.ShopLoyalty.query").filter_by.return_value.first.return_value = None
    acct = MagicMock(id=3)
    mocker.patch(
        "models.shop_customer_account.ShopCustomerAccount.query"
    ).filter_by.return_value.first.return_value = acct
    add = mocker.patch("extensions.db.session.add")
    online_sale.customer_id = 1
    StoreOrderService._reverse_loyalty_points(online_sale)
    assert add.called


def test_reverse_loyalty_without_account(mocker, online_sale):
    from services.store_order_service import StoreOrderService

    txn = MagicMock(points=25)
    mocker.patch("models.shop_loyalty.ShopLoyaltyTransaction.query").filter_by.return_value.first.return_value = txn
    mocker.patch(
        "models.shop_customer_account.ShopCustomerAccount.query"
    ).filter_by.return_value.first.return_value = None
    online_sale.customer_id = 1
    assert StoreOrderService._reverse_loyalty_points(online_sale) is None


def test_cancel_confirmed_without_coupon(mocker, online_sale, app):
    from services.store_order_service import StoreOrderService

    mocker.patch(
        "services.store_order_service.SaleService.has_inventory_posted",
        return_value=True,
    )
    online_sale.status = "confirmed"
    online_sale.coupon_code = None
    cancel = mocker.patch("services.store_order_service.SaleService.cancel_sale")
    with app.app_context():
        result = StoreOrderService.cancel_order(online_sale)
    cancel.assert_called_once_with(online_sale)
    assert result.status == "confirmed"
