from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from services.store_order_service import StoreOrderService


class TestLabelsAndQueries:
    def test_status_label_ar_and_en(self):
        assert StoreOrderService.status_label("pending", "ar") == "بانتظار التأكيد"
        assert StoreOrderService.status_label("shipped", "en") == "Shipped"
        assert StoreOrderService.status_label("unknown", "ar") == "unknown"

    def test_is_online_order(self, online_sale):
        assert StoreOrderService.is_online_order(online_sale) is True
        assert StoreOrderService.is_online_order(MagicMock(source="pos")) is False

    def test_get_tenant_order_scoped(self, db_session, online_sale, sample_tenant):
        found = StoreOrderService.get_tenant_order(sample_tenant.id, online_sale.id)
        assert found is not None
        assert StoreOrderService.get_tenant_order(sample_tenant.id, 999999999) is None

    def test_list_for_customer(
        self, db_session, online_sale, sample_tenant, sample_customer
    ):
        rows = StoreOrderService.list_for_customer(sample_tenant.id, sample_customer.id)
        assert any(s.id == online_sale.id for s in rows)

    def test_order_counts(self, db_session, online_sale, sample_tenant):
        counts = StoreOrderService.order_counts(sample_tenant.id)
        assert counts["pending"] >= 1
        assert counts["total"] >= 1


class TestConfirmOrder:
    def test_rejects_non_online(self, sample_sale):
        with pytest.raises(ValueError, match="متجر"):
            StoreOrderService.confirm_order(sample_sale)

    def test_rejects_cancelled(self, online_sale):
        online_sale.status = "cancelled"
        with pytest.raises(ValueError, match="ملغى"):
            StoreOrderService.confirm_order(online_sale)

    def test_rejects_already_fulfilled(self, mocker, online_sale):
        online_sale.status = "confirmed"
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        with pytest.raises(ValueError, match="مؤكد"):
            StoreOrderService.confirm_order(online_sale)

    def test_confirms_pending_order(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=False,
        )
        mocker.patch("services.store_order_service.SaleService.fulfill_sale")
        with app.app_context():
            result = StoreOrderService.confirm_order(online_sale)
        assert result.status == "confirmed"

    def test_mark_paid_cod(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        payment = MagicMock()
        mocker.patch(
            "services.store_order_service.SaleService.create_payment_for_sale",
            return_value=payment,
        )
        online_sale.balance_due = Decimal("0")
        online_sale.total_amount = Decimal("100")
        online_sale.checkout_payment_method = "cod"
        online_sale.recalculate_payment_status = MagicMock()
        with app.app_context():
            StoreOrderService.confirm_order(online_sale, mark_paid=True)
        online_sale.recalculate_payment_status.assert_called_once()

    def test_mark_paid_normalizes_cod_alias(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        pay = mocker.patch(
            "services.store_order_service.SaleService.create_payment_for_sale",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.store_order_service.normalize_payment_method_code",
            return_value="cod",
        )
        online_sale.total_amount = Decimal("80")
        online_sale.balance_due = Decimal("80")
        online_sale.checkout_payment_method = "wire"
        online_sale.recalculate_payment_status = MagicMock()
        with app.app_context():
            StoreOrderService.confirm_order(online_sale, mark_paid=True)
        assert pay.call_args.kwargs["payment_method"] == "cash"

    def test_confirm_commit_failure(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with app.app_context():
            with pytest.raises(RuntimeError):
                StoreOrderService.confirm_order(online_sale)

    def test_award_loyalty_skips_without_customer(self, mocker):
        earn = mocker.patch("services.store_service.StoreService.earn_loyalty_points")
        sale = MagicMock(customer_id=None)
        StoreOrderService._award_loyalty_points(sale)
        earn.assert_not_called()

    def test_mark_paid_online_pay_records_fee(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        payment = MagicMock()
        mocker.patch(
            "services.store_order_service.SaleService.create_payment_for_sale",
            return_value=payment,
        )
        fee_mock = mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee",
        )
        online_sale.total_amount = Decimal("200")
        online_sale.balance_due = Decimal("200")
        online_sale.checkout_payment_method = "online_pay"
        online_sale.recalculate_payment_status = MagicMock()
        with app.app_context():
            StoreOrderService.confirm_order(online_sale, mark_paid=True)
        fee_mock.assert_called_once()

    def test_award_loyalty_idempotent(self, mocker, online_sale):
        earn = mocker.patch("services.store_service.StoreService.earn_loyalty_points")
        txn_q = mocker.patch("models.shop_loyalty.ShopLoyaltyTransaction.query")
        txn_q.filter_by.return_value.first.side_effect = [None, MagicMock()]
        acct_q = mocker.patch("models.shop_customer_account.ShopCustomerAccount.query")
        acct_q.filter_by.return_value.first.return_value = MagicMock(id=1)
        online_sale.customer_id = 1
        online_sale.total_amount = Decimal("50")
        StoreOrderService._award_loyalty_points(online_sale)
        StoreOrderService._award_loyalty_points(online_sale)
        assert earn.call_count == 1


class TestCancelOrder:
    def test_rejects_non_online(self, sample_sale):
        with pytest.raises(ValueError, match="متجر"):
            StoreOrderService.cancel_order(sample_sale)

    def test_rejects_already_cancelled(self, online_sale):
        online_sale.status = "cancelled"
        with pytest.raises(ValueError, match="ملغى"):
            StoreOrderService.cancel_order(online_sale)

    def test_cancel_pending(self, mocker, online_sale, app):
        release = mocker.patch(
            "services.store_coupon_service.StoreCouponService.release_use"
        )
        online_sale.coupon_code = "SAVE10"
        with app.app_context():
            result = StoreOrderService.cancel_order(online_sale)
        assert result.status == "cancelled"
        release.assert_called_once()

    def test_cancel_fulfilled_delegates_to_sale_service(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        online_sale.status = "confirmed"
        cancel = mocker.patch("services.store_order_service.SaleService.cancel_sale")
        release = mocker.patch(
            "services.store_coupon_service.StoreCouponService.release_use"
        )
        online_sale.coupon_code = "CPN"
        with app.app_context():
            StoreOrderService.cancel_order(online_sale)
        cancel.assert_called_once_with(online_sale)
        release.assert_called_once()


class TestReverseLoyalty:
    def test_reverse_loyalty_full_path(self, mocker, online_sale):
        txn = MagicMock(points=25)
        mocker.patch(
            "models.shop_loyalty.ShopLoyaltyTransaction.query"
        ).filter_by.return_value.first.return_value = txn
        lp = MagicMock(points=50, points_earned=50)
        mocker.patch(
            "models.shop_loyalty.ShopLoyalty.query"
        ).filter_by.return_value.first.return_value = lp
        acct = MagicMock(id=3)
        mocker.patch(
            "models.shop_customer_account.ShopCustomerAccount.query"
        ).filter_by.return_value.first.return_value = acct
        add = mocker.patch("extensions.db.session.add")
        online_sale.customer_id = 1
        StoreOrderService._reverse_loyalty_points(online_sale)
        assert lp.points == 25
        assert add.called

    def test_reverse_loyalty_no_customer(self, online_sale):
        online_sale.customer_id = None
        StoreOrderService._reverse_loyalty_points(online_sale)


class TestCancelCommitFailures:
    def test_cancel_fulfilled_coupon_commit_failure(self, mocker, online_sale, app):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        online_sale.status = "confirmed"
        online_sale.coupon_code = "CPN"
        mocker.patch("services.store_order_service.SaleService.cancel_sale")
        mocker.patch("services.store_coupon_service.StoreCouponService.release_use")
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with app.app_context():
            with pytest.raises(RuntimeError):
                StoreOrderService.cancel_order(online_sale)

    def test_cancel_pending_commit_failure(self, mocker, online_sale, app):
        mocker.patch("services.store_coupon_service.StoreCouponService.release_use")
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with app.app_context():
            with pytest.raises(RuntimeError):
                StoreOrderService.cancel_order(online_sale)


class TestValidateStock:
    def test_no_issues_when_stock_ok(self, mocker):
        mocker.patch(
            "services.store_order_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        sale = MagicMock(warehouse_id=1)
        line = MagicMock(
            product_id=1, quantity=Decimal("1"), product=MagicMock(name="P")
        )
        sale.lines = [line]
        assert StoreOrderService.validate_stock_for_order(sale) == []

    def test_collects_stock_issues(self, mocker):
        mocker.patch(
            "services.store_order_service.StockService.check_availability_in_warehouse",
            return_value=(False, "نفد"),
        )
        sale = MagicMock(warehouse_id=1)
        product = MagicMock()
        product.name = "Widget"
        line = MagicMock(product_id=1, quantity=Decimal("5"), product=product)
        sale.lines = [line]
        issues = StoreOrderService.validate_stock_for_order(sale)
        assert issues == ["Widget: نفد"]
