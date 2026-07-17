from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import Customer
from models.shop_customer_account import ShopCustomerAccount
from services.shop_customer_auth_service import ShopCustomerAuthService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _account(db_session, tenant_id, email=None, password="secret12", **kwargs):
    email = email or f"{uuid.uuid4().hex[:8]}@shop.test"
    customer = Customer(
        tenant_id=tenant_id,
        name=kwargs.get("name", "Shop Buyer"),
        customer_type="regular",
        phone=kwargs.get("phone", "05012345678"),
        email=email,
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()
    account = ShopCustomerAccount(
        tenant_id=tenant_id,
        customer_id=customer.id,
        email=email,
        phone=customer.phone,
        name=customer.name,
        is_active=kwargs.get("is_active", True),
    )
    account.set_password(password)
    db.session.add(account)
    db.session.flush()
    return account


class TestSessionHelpers:
    def test_session_key_format(self):
        assert ShopCustomerAuthService.session_key(7) == "shop_account_7"

    def test_login_logout_round_trip(self, app):
        session_obj = MagicMock()
        account = MagicMock(id=55)
        ShopCustomerAuthService.login(session_obj, 3, account)
        session_obj.__setitem__.assert_called_with("shop_account_3", 55)
        assert session_obj.modified is True
        ShopCustomerAuthService.logout(session_obj, 3)
        session_obj.pop.assert_called_with("shop_account_3", None)

    def test_get_logged_in_account_missing_session(self, app):
        with app.test_request_context():
            assert ShopCustomerAuthService.get_logged_in_account(1) is None

    def test_get_logged_in_account_wrong_tenant(self, app, db_session, sample_tenant):
        account = _account(db_session, sample_tenant.id)
        with app.test_request_context() as ctx:
            ctx.session["shop_account_1"] = account.id
            assert ShopCustomerAuthService.get_logged_in_account(2) is None

    def test_get_logged_in_account_inactive(self, app, db_session, sample_tenant):
        account = _account(db_session, sample_tenant.id, is_active=False)
        with app.test_request_context() as ctx:
            ctx.session[f"shop_account_{sample_tenant.id}"] = account.id
            assert (
                ShopCustomerAuthService.get_logged_in_account(sample_tenant.id) is None
            )

    def test_get_logged_in_account_valid(self, app, db_session, sample_tenant):
        account = _account(db_session, sample_tenant.id)
        with app.test_request_context() as ctx:
            ctx.session[f"shop_account_{sample_tenant.id}"] = account.id
            loaded = ShopCustomerAuthService.get_logged_in_account(sample_tenant.id)
            assert loaded is not None
            assert loaded.id == account.id


class TestNormalization:
    def test_normalize_email_valid(self):
        assert (
            ShopCustomerAuthService.normalize_email("  User@Example.COM ")
            == "user@example.com"
        )

    def test_normalize_email_invalid(self):
        with pytest.raises(ValueError, match="البريد"):
            ShopCustomerAuthService.normalize_email("not-an-email")

    def test_normalize_phone_valid(self):
        assert (
            ShopCustomerAuthService.normalize_phone("+971 50 123 4567")
            == "971501234567"
        )

    def test_normalize_phone_too_short(self):
        with pytest.raises(ValueError, match="الهاتف"):
            ShopCustomerAuthService.normalize_phone("123")


class TestRegisterAuthenticate:
    def test_register_creates_account(self, db_session, sample_tenant):
        account = ShopCustomerAuthService.register(
            sample_tenant.id,
            "New Shopper",
            "new@shop.test",
            "05099998888",
            "pass1234",
        )
        assert account.id is not None
        assert account.email == "new@shop.test"

    def test_register_reuses_existing_customer_phone(self, db_session, sample_tenant):
        customer = Customer(
            tenant_id=sample_tenant.id,
            name="Old Name",
            customer_type="regular",
            phone="05077776666",
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()
        account = ShopCustomerAuthService.register(
            sample_tenant.id,
            "Updated Name",
            "other@shop.test",
            "05077776666",
            "pass1234",
        )
        assert account.customer_id == customer.id
        assert customer.name == "Updated Name"

    def test_register_duplicate_email_raises(self, db_session, sample_tenant):
        _account(db_session, sample_tenant.id, email="dup@shop.test")
        with pytest.raises(ValueError, match="مسجّل"):
            ShopCustomerAuthService.register(
                sample_tenant.id,
                "Dup",
                "dup@shop.test",
                "05011112222",
                "pass1234",
            )

    def test_authenticate_success_updates_last_login(self, db_session, sample_tenant):
        account = _account(
            db_session, sample_tenant.id, email="auth@shop.test", password="mypass12"
        )
        result = ShopCustomerAuthService.authenticate(
            sample_tenant.id, "auth@shop.test", "mypass12"
        )
        assert result.id == account.id
        assert result.last_login_at is not None

    def test_authenticate_wrong_password(self, db_session, sample_tenant):
        _account(
            db_session, sample_tenant.id, email="bad@shop.test", password="correct1"
        )
        with pytest.raises(ValueError, match="بيانات الدخول"):
            ShopCustomerAuthService.authenticate(
                sample_tenant.id, "bad@shop.test", "wrongpass"
            )


class TestPasswordReset:
    def test_request_password_reset_unknown_email(self, sample_tenant):
        assert (
            ShopCustomerAuthService.request_password_reset(
                sample_tenant.id, "nobody@shop.test"
            )
            is None
        )

    def test_request_password_reset_sets_token(self, db_session, sample_tenant):
        _account(db_session, sample_tenant.id, email="reset@shop.test")
        updated = ShopCustomerAuthService.request_password_reset(
            sample_tenant.id, "reset@shop.test"
        )
        assert updated.password_reset_token
        assert updated.password_reset_expires_at is not None

    def test_reset_password_success(self, db_session, sample_tenant):
        account = _account(db_session, sample_tenant.id, email="tok@shop.test")
        account.password_reset_token = "valid-token"
        account.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=1
        )
        db.session.commit()
        result = ShopCustomerAuthService.reset_password(
            sample_tenant.id, "valid-token", "newpass99"
        )
        assert result.password_reset_token is None
        assert result.check_password("newpass99")

    def test_reset_password_expired_token(self, db_session, sample_tenant):
        account = _account(db_session, sample_tenant.id, email="exp@shop.test")
        account.password_reset_token = "expired-token"
        account.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(
            hours=1
        )
        db.session.commit()
        with pytest.raises(ValueError, match="انتهت"):
            ShopCustomerAuthService.reset_password(
                sample_tenant.id, "expired-token", "newpass99"
            )

    def test_reset_password_empty_token(self, sample_tenant):
        with pytest.raises(ValueError, match="رمز"):
            ShopCustomerAuthService.reset_password(sample_tenant.id, "", "newpass99")

    def test_send_password_reset_email_no_mail_config(
        self, app, db_session, sample_tenant
    ):
        account = _account(db_session, sample_tenant.id)
        store = MagicMock(title="Test Store")
        with app.app_context():
            assert (
                ShopCustomerAuthService.send_password_reset_email(
                    account, store, "http://reset"
                )
                is False
            )

    def test_send_password_reset_email_success(
        self, app, db_session, sample_tenant, mocker
    ):
        account = _account(db_session, sample_tenant.id)
        store = MagicMock(title="Test Store")
        app.config["MAIL_USERNAME"] = "user"
        app.config["MAIL_PASSWORD"] = "pass"
        mock_mail = MagicMock()
        mocker.patch("extensions.mail", mock_mail)
        mocker.patch("flask_mail.Message")
        with app.app_context():
            assert (
                ShopCustomerAuthService.send_password_reset_email(
                    account, store, "http://reset"
                )
                is True
            )
        mock_mail.send.assert_called_once()

    def test_send_password_reset_email_failure_logged(
        self, app, db_session, sample_tenant, mocker
    ):
        account = _account(db_session, sample_tenant.id)
        store = MagicMock(title="Test Store")
        app.config["MAIL_USERNAME"] = "user"
        app.config["MAIL_PASSWORD"] = "pass"
        mock_mail = MagicMock()
        mock_mail.send.side_effect = RuntimeError("smtp fail")
        mocker.patch("extensions.mail", mock_mail)
        mocker.patch("flask_mail.Message")
        with app.app_context():
            logger = MagicMock()
            mocker.patch("flask.current_app.logger", logger)
            assert (
                ShopCustomerAuthService.send_password_reset_email(
                    account, store, "http://reset"
                )
                is False
            )
        logger.warning.assert_called()


class TestWhatsappOrderUrl:
    def test_returns_none_without_phone(self):
        store = MagicMock(whatsapp="", phone="", title="Shop", tenant=None)
        product = MagicMock()
        product.get_display_name.return_value = "Item"
        product.sku = "SKU1"
        product.regular_price = 10
        assert ShopCustomerAuthService.whatsapp_order_url(store, product) is None

    def test_arabic_url(self, mocker):
        mocker.patch(
            "services.shop_customer_auth_service.resolve_default_currency",
            return_value="AED",
        )
        store = MagicMock(
            whatsapp="+971501234567", phone=None, title="متجري", tenant=None
        )
        product = MagicMock()
        product.get_display_name.return_value = "منتج"
        product.sku = "P1"
        product.regular_price = 99
        url = ShopCustomerAuthService.whatsapp_order_url(store, product, "ar", 2)
        assert url.startswith("https://wa.me/971501234567")
        assert "text=" in url

    def test_english_url(self, mocker):
        mocker.patch(
            "services.shop_customer_auth_service.resolve_default_currency",
            return_value="AED",
        )
        store = MagicMock(
            whatsapp="971509876543", phone=None, title="My Shop", tenant=None
        )
        product = MagicMock()
        product.get_display_name.return_value = "Widget"
        product.sku = None
        product.regular_price = 50
        url = ShopCustomerAuthService.whatsapp_order_url(store, product, "en", 1)
        assert "Hello" in url or "text=" in url
