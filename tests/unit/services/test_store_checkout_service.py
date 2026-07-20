from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from services.store_checkout_service import StoreCheckoutService
from utils.db_safety import atomic_transaction


class TestOrderTokens:
    def test_round_trip_token(self, app):
        with app.app_context():
            token = StoreCheckoutService.make_order_token(42, 7)
            data = StoreCheckoutService.load_order_token(token)
        assert data == {"sale_id": 42, "tenant_id": 7}

    def test_invalid_token_returns_none(self, app):
        with app.app_context():
            assert StoreCheckoutService.load_order_token("not-a-token") is None

    def test_production_requires_secret(self, app):
        old_secret = app.config.get("SECRET_KEY")
        try:
            app.config["DEBUG"] = False
            app.config["APP_ENV"] = "production"
            app.config["SECRET_KEY"] = None
            with app.app_context():
                with pytest.raises(ValueError, match="SECRET_KEY"):
                    StoreCheckoutService.make_order_token(1, 1)
        finally:
            app.config["SECRET_KEY"] = old_secret

    def test_dev_fallback_secret(self, app):
        old_secret = app.config.get("SECRET_KEY")
        try:
            app.config["DEBUG"] = True
            app.config["SECRET_KEY"] = None
            with app.app_context():
                token = StoreCheckoutService.make_order_token(1, 2)
                assert StoreCheckoutService.load_order_token(token) is not None
        finally:
            app.config["SECRET_KEY"] = old_secret


class TestNormalizePhone:
    def test_strips_and_validates(self):
        assert StoreCheckoutService.normalize_phone("+971 50 123 4567") == "971501234567"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="مطلوب"):
            StoreCheckoutService.normalize_phone("")

    def test_short_raises(self):
        with pytest.raises(ValueError, match="غير صالح"):
            StoreCheckoutService.normalize_phone("1234567")


class TestCustomerAndSeller:
    def test_get_or_create_customer(self, db_session, sample_tenant):
        c1 = StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "Buyer One",
            "05012345678",
            address="Addr",
        )
        c2 = StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "Buyer Updated",
            "05012345678",
            email="b@t.com",
        )
        assert c1.id == c2.id
        assert c2.name == "Buyer Updated"
        assert c2.email == "b@t.com"

    def test_short_name_raises(self, sample_tenant):
        with pytest.raises(ValueError, match="الاسم"):
            StoreCheckoutService.get_or_create_customer(sample_tenant.id, "X", "05012345678")

    def test_resolve_seller_owner_first(self, db_session, sample_tenant, sample_user):
        sample_user.is_owner = True
        db_session.flush()
        seller = StoreCheckoutService.resolve_seller(sample_tenant.id)
        assert seller.id == sample_user.id

    def test_resolve_seller_missing_raises(self, db_session, sample_tenant):
        from models import User

        User.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        with pytest.raises(ValueError, match="مستخدم"):
            StoreCheckoutService.resolve_seller(sample_tenant.id)


class TestBuildLinesFromCart:
    def test_empty_cart_raises(self, sample_tenant, online_warehouse):
        with pytest.raises(ValueError, match="فارغة"):
            StoreCheckoutService.build_lines_from_cart(sample_tenant.id, {}, online_warehouse.id)

    def test_builds_line_with_stock(
        self,
        mocker,
        sample_tenant,
        online_warehouse,
        sample_product_with_stock,
    ):
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("50")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        cart = {str(sample_product_with_stock.id): 2}
        lines = StoreCheckoutService.build_lines_from_cart(
            sample_tenant.id,
            cart,
            online_warehouse.id,
        )
        assert len(lines) == 1
        assert lines[0]["quantity"] == 2.0

    def test_serial_product_rejected(
        self,
        mocker,
        db_session,
        sample_tenant,
        online_warehouse,
        sample_product_with_stock,
    ):
        sample_product_with_stock.has_serial_number = True
        db_session.flush()
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        with pytest.raises(ValueError, match="الهاتف"):
            StoreCheckoutService.build_lines_from_cart(
                sample_tenant.id,
                {str(sample_product_with_stock.id): 1},
                online_warehouse.id,
            )

    def test_insufficient_stock_raises(
        self,
        mocker,
        sample_tenant,
        online_warehouse,
        sample_product_with_stock,
    ):
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("1")},
        )
        with pytest.raises(ValueError, match="تتجاوز"):
            StoreCheckoutService.build_lines_from_cart(
                sample_tenant.id,
                {str(sample_product_with_stock.id): 5},
                online_warehouse.id,
            )


class TestCreateWebOrder:
    def test_missing_online_warehouse_raises(self, tenant_store, mocker):
        mocker.patch("extensions.db.session.get", return_value=None)
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        with pytest.raises(ValueError, match="مستودع"):
            StoreCheckoutService.create_web_order(
                tenant_store,
                {"1": 1},
                "Name",
                "05012345678",
                "Addr",
            )

    def test_creates_sale_without_coupon(
        self,
        mocker,
        tenant_store,
        sample_tenant,
        sample_user,
        sample_product_with_stock,
        online_warehouse,
    ):
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("20")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        sale_mock = MagicMock(id=99, sale_number="S-1")
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=sale_mock,
        )
        notify = mocker.patch(
            "services.store_notification_service.StoreNotificationService.notify_new_order",
        )
        sample_user.is_owner = True
        cart = {str(sample_product_with_stock.id): 1}
        sale = StoreCheckoutService.create_web_order(
            tenant_store,
            cart,
            "Web Buyer",
            "05098765432",
            "Delivery St",
        )
        assert sale is sale_mock
        notify.assert_called_once_with(sale_mock, tenant_store)

    def test_coupon_path_marks_used(
        self,
        mocker,
        tenant_store,
        sample_tenant,
        sample_user,
        sample_product_with_stock,
    ):
        from models.store_coupon import StoreCoupon

        coupon = StoreCoupon(
            tenant_id=sample_tenant.id,
            code="WEB10",
            discount_amount=Decimal("5"),
            is_active=True,
        )
        db.session.add(coupon)
        db.session.flush()

        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("20")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        sale_mock = MagicMock(id=100)
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=sale_mock,
        )
        mocker.patch(
            "services.store_notification_service.StoreNotificationService.notify_new_order",
        )
        mark = mocker.patch("services.store_coupon_service.StoreCouponService.mark_used")
        sample_user.is_owner = True
        StoreCheckoutService.create_web_order(
            tenant_store,
            {str(sample_product_with_stock.id): 2},
            "Coupon User",
            "05011112222",
            "Addr",
            coupon_code="WEB10",
        )
        mark.assert_called_once()

    def test_shop_account_existing_customer(
        self,
        mocker,
        tenant_store,
        sample_customer,
        sample_user,
        sample_product_with_stock,
    ):
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        sale_mock = MagicMock()
        create = mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=sale_mock,
        )
        mocker.patch(
            "services.store_notification_service.StoreNotificationService.notify_new_order",
        )
        account = MagicMock(customer_id=sample_customer.id)
        sample_user.is_owner = True
        StoreCheckoutService.create_web_order(
            tenant_store,
            {str(sample_product_with_stock.id): 1},
            "Acct User",
            "05033334444",
            "Addr",
            shop_account=account,
        )
        assert create.call_args.kwargs["customer"].id == sample_customer.id

    def test_load_order_token_non_dict_returns_none(self, app):
        with app.app_context():
            token = StoreCheckoutService._serializer().dumps(["not", "a", "dict"])
            assert StoreCheckoutService.load_order_token(token) is None

    def test_build_lines_skips_invalid_qty(self, mocker, sample_tenant, online_warehouse, sample_product_with_stock):
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        cart = {str(sample_product_with_stock.id): 0, "999": -1}
        with pytest.raises(ValueError, match="فارغة"):
            StoreCheckoutService.build_lines_from_cart(
                sample_tenant.id,
                cart,
                online_warehouse.id,
            )

    def test_get_or_create_customer_updates_existing_email(self, db_session, sample_tenant):
        customer = StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "First",
            "05055556666",
        )
        updated = StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "Renamed",
            "05055556666",
            email="new@mail.test",
        )
        assert updated.id == customer.id
        assert updated.name == "Renamed"
        assert updated.email == "new@mail.test"

    def test_shop_account_missing_customer_recreates(
        self,
        mocker,
        tenant_store,
        sample_user,
        sample_product_with_stock,
        online_warehouse,
    ):
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )

        def get_side_effect(model, pk):
            from models import Warehouse as WH

            if model is WH:
                return online_warehouse
            return None

        mocker.patch("extensions.db.session.get", side_effect=get_side_effect)
        create_customer = mocker.patch(
            "services.store_checkout_service.StoreCheckoutService.get_or_create_customer",
            return_value=MagicMock(id=1),
        )
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=MagicMock(id=1),
        )
        mocker.patch("services.store_notification_service.StoreNotificationService.notify_new_order")
        sample_user.is_owner = True
        account = MagicMock(customer_id=999)
        StoreCheckoutService.create_web_order(
            tenant_store,
            {str(sample_product_with_stock.id): 1},
            "Ghost",
            "05044443333",
            "Addr",
            shop_account=account,
        )
        create_customer.assert_called_once()

    def test_create_web_order_with_notes_and_email(
        self,
        mocker,
        tenant_store,
        sample_user,
        sample_product_with_stock,
    ):
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        sale_mock = MagicMock(id=200)
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=sale_mock,
        )
        mocker.patch("services.store_notification_service.StoreNotificationService.notify_new_order")
        sample_user.is_owner = True
        StoreCheckoutService.create_web_order(
            tenant_store,
            {str(sample_product_with_stock.id): 1},
            "Note User",
            "05022221111",
            "Addr",
            notes="Leave at door",
            customer_email="note@test.com",
        )

    def test_coupon_commit_failure_rolls_back(
        self,
        mocker,
        tenant_store,
        sample_tenant,
        sample_user,
        sample_product_with_stock,
    ):
        from models.store_coupon import StoreCoupon

        coupon = StoreCoupon(
            tenant_id=sample_tenant.id,
            code="FAIL10",
            discount_amount=Decimal("5"),
            is_active=True,
        )
        db.session.add(coupon)
        db.session.flush()
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=MagicMock(id=1),
        )
        mocker.patch("services.store_notification_service.StoreNotificationService.notify_new_order")
        mocker.patch("services.store_coupon_service.StoreCouponService.mark_used")
        mocker.patch("extensions.db.session.flush", side_effect=RuntimeError("flush fail"))
        rollback = mocker.patch("extensions.db.session.rollback")
        sample_user.is_owner = True
        with pytest.raises(RuntimeError):
            with atomic_transaction("test_coupon_fail"):
                StoreCheckoutService.create_web_order(
                    tenant_store,
                    {str(sample_product_with_stock.id): 1},
                    "Coupon Fail",
                    "05088887777",
                    "Addr",
                    coupon_code="FAIL10",
                )
        rollback.assert_called()

    def test_get_or_create_customer_sets_address_when_empty(self, db_session, sample_tenant):
        StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "Addr User",
            "05066667777",
        )
        updated = StoreCheckoutService.get_or_create_customer(
            sample_tenant.id,
            "Addr User",
            "05066667777",
            address="New Street",
        )
        assert updated.address == "New Street"

    def test_build_lines_skips_unparseable_product_id(
        self, mocker, sample_tenant, online_warehouse, sample_product_with_stock
    ):
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        lines = StoreCheckoutService.build_lines_from_cart(
            sample_tenant.id,
            {"bad-id": 1, str(sample_product_with_stock.id): 1},
            online_warehouse.id,
        )
        assert len(lines) == 1

    def test_shop_account_updates_customer_email(
        self,
        mocker,
        tenant_store,
        sample_customer,
        sample_user,
        sample_product_with_stock,
        online_warehouse,
    ):
        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("10")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        mocker.patch(
            "services.store_checkout_service.SaleService.create_sale",
            return_value=MagicMock(id=1),
        )
        mocker.patch("services.store_notification_service.StoreNotificationService.notify_new_order")

        def get_side_effect(model, pk):
            from models import Warehouse as WH, Customer as C

            if model is WH:
                return online_warehouse
            if model is C:
                return sample_customer
            return None

        mocker.patch("extensions.db.session.get", side_effect=get_side_effect)
        sample_customer.email = None
        sample_user.is_owner = True
        account = MagicMock(customer_id=sample_customer.id)
        StoreCheckoutService.create_web_order(
            tenant_store,
            {str(sample_product_with_stock.id): 1},
            "Email User",
            "05033334444",
            "Addr",
            shop_account=account,
            customer_email="newbuyer@test.com",
        )
        assert sample_customer.email == "newbuyer@test.com"
