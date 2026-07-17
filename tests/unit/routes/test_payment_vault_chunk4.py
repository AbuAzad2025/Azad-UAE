from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_db(mock_db):
    pass


@pytest.fixture
def mock_unlocked_vault(mocker):
    vault = MagicMock()
    vault.id = 1
    vault.is_locked = False
    vault.is_vault_accessible.return_value = True
    vault.unlock_vault.return_value = True
    vault.is_locked_out.return_value = False
    vault.check_vault_password.return_value = True
    vault.nowpayments_api_key = ""
    vault.nowpayments_ipn_secret = "sec"
    vault.stripe_webhook_secret = "whsec"
    vault.min_donation_amount = 5.0
    vault.max_donation_amount = 1000.0
    vault.daily_limit = 5000.0
    vault.auto_lock_minutes = 30
    vault.max_failed_attempts = 5
    mocker.patch(
        "routes.payment_vault._get_vault_for_current_tenant", return_value=vault
    )
    mocker.patch(
        "routes.payment_vault.PaymentVault.get_platform_vault", return_value=vault
    )
    return vault


@pytest.fixture(autouse=True)
def _patch_render(mocker):
    mocker.patch("routes.payment_vault.render_template", return_value="ok")


class TestSettingsPostBranches:
    def test_settings_post_invalid_numeric_defaults(
        self, vault_owner_client, mock_unlocked_vault, mocker
    ):
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/settings",
            data={
                "min_donation_amount": "bad",
                "max_donation_amount": "",
                "daily_limit": "x",
                "auto_lock_minutes": "nope",
                "max_failed_attempts": "",
                "donations_enabled": "on",
                "donation_page_enabled": "on",
                "donation_debit_account": "1120",
                "donation_credit_account": "4200",
                "require_2fa": "on",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)

    def test_settings_get_unlocked(self, vault_owner_client, mock_unlocked_vault):
        resp = vault_owner_client.get("/payment-vault/settings")
        assert resp.status_code == 200


class TestChangePasswordPost:
    def test_change_password_empty_fields(
        self, vault_owner_client, mock_unlocked_vault
    ):
        resp = vault_owner_client.post(
            "/payment-vault/change-password",
            data={
                "current_password": "",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
        )
        assert resp.status_code == 200

    def test_change_password_wrong_current(
        self, vault_owner_client, mock_unlocked_vault
    ):
        mock_unlocked_vault.check_vault_password.return_value = False
        resp = vault_owner_client.post(
            "/payment-vault/change-password",
            data={
                "current_password": "wrong",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
        )
        assert resp.status_code == 200

    def test_change_password_mismatch(self, vault_owner_client, mock_unlocked_vault):
        resp = vault_owner_client.post(
            "/payment-vault/change-password",
            data={
                "current_password": "oldpass12",
                "new_password": "newpass12",
                "confirm_password": "different",
            },
        )
        assert resp.status_code == 200

    def test_change_password_too_short(self, vault_owner_client, mock_unlocked_vault):
        resp = vault_owner_client.post(
            "/payment-vault/change-password",
            data={
                "current_password": "oldpass12",
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert resp.status_code == 200

    def test_change_password_success(
        self, vault_owner_client, mock_unlocked_vault, mocker
    ):
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/change-password",
            data={
                "current_password": "oldpass12",
                "new_password": "newpass99",
                "confirm_password": "newpass99",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)
        mock_unlocked_vault.set_vault_password.assert_called_once_with("newpass99")


class TestWebhook500Handlers:
    PAYLOAD = b'{"id":"evt_fail","type":"payment_intent.succeeded","created_at":"2026-06-27T12:00:00+00:00"}'
    NP_PAYLOAD = b'{"payment_id":"np1","payment_status":"finished","created_at":"2026-06-27T12:00:00+00:00"}'

    def test_stripe_webhook_processing_exception(
        self, vault_owner_client, mock_unlocked_vault, mocker
    ):
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        mocker.patch(
            "routes.payment_vault._reject_stale_webhook_timestamp", return_value=None
        )
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_stripe_webhook",
            side_effect=RuntimeError("processor down"),
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"Stripe-Signature": "good"},
        )
        assert resp.status_code == 500

    def test_nowpayments_webhook_processing_exception(
        self, vault_owner_client, mock_unlocked_vault, mocker
    ):
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        mocker.patch(
            "routes.payment_vault._reject_stale_webhook_timestamp", return_value=None
        )
        mocker.patch(
            "services.webhook_service.WebhookService.verify_nowpayments_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_nowpayments_webhook",
            side_effect=RuntimeError("np fail"),
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.NP_PAYLOAD,
            content_type="application/json",
            headers={"x-nowpayments-sig": "sig"},
        )
        assert resp.status_code == 500


class TestProcessPayment500:
    ENDPOINT = "/payment-vault/process-payment"

    def test_outer_exception_returns_500(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault.NOWPaymentsService",
            side_effect=RuntimeError("service init fail"),
        )
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={"payment_method": "crypto", "amount": 100, "crypto_currency": "btc"},
        )
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


class TestPurchaseDonationApi500:
    PURCHASE = "/payment-vault/api/purchase"
    DONATION = "/payment-vault/api/donation"
    PURCHASE_DATA = {
        "package_id": 1,
        "customer_name": "Ali",
        "customer_email": "ali@test.com",
        "payment_method": "bank",
        "amount_paid": 100,
    }
    DONATION_DATA = {"amount": 50, "payment_method": "crypto", "crypto_type": "btc"}

    @pytest.fixture(autouse=True)
    def _patch_security(self, mocker):
        mocker.patch(
            "routes.payment_vault._validate_public_api_origin", return_value=None
        )
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        mocker.patch("routes.payment_vault._check_idempotency_key", return_value=None)

    def test_purchase_api_exception_returns_500(
        self, vault_owner_client, mocker, mock_db
    ):
        mocker.patch(
            "routes.payment_vault.db.session.get", side_effect=RuntimeError("db down")
        )
        resp = vault_owner_client.post(self.PURCHASE, json=self.PURCHASE_DATA)
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False

    def test_donation_api_exception_returns_500(
        self, vault_owner_client, mocker, mock_db
    ):
        mocker.patch("routes.payment_vault.NOWPaymentsService")
        mock_db.session.commit.side_effect = RuntimeError("commit fail")
        resp = vault_owner_client.post(self.DONATION, json=self.DONATION_DATA)
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


class TestPurchaseDonationApiValidation:
    PURCHASE = "/payment-vault/api/purchase"
    DONATION = "/payment-vault/api/donation"

    @pytest.fixture(autouse=True)
    def _patch_security(self, mocker):
        mocker.patch(
            "routes.payment_vault._validate_public_api_origin", return_value=None
        )
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        mocker.patch("routes.payment_vault._check_idempotency_key", return_value=None)

    def test_purchase_missing_required_field(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.PURCHASE,
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
            },
        )
        assert resp.status_code == 400

    def test_purchase_invalid_email(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.PURCHASE,
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "bad",
                "payment_method": "bank",
                "amount_paid": 100,
            },
        )
        assert resp.status_code == 400

    def test_purchase_inactive_package(self, vault_owner_client, mocker):
        pkg = MagicMock(is_active=False)
        mocker.patch("routes.payment_vault.db.session.get", return_value=pkg)
        resp = vault_owner_client.post(
            self.PURCHASE,
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "bank",
                "amount_paid": 100,
            },
        )
        assert resp.status_code == 404

    def test_purchase_amount_too_low(self, vault_owner_client, mocker):
        pkg = MagicMock(is_active=True, price=200)
        mocker.patch("routes.payment_vault.db.session.get", return_value=pkg)
        resp = vault_owner_client.post(
            self.PURCHASE,
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "bank",
                "amount_paid": 50,
            },
        )
        assert resp.status_code == 400

    def test_donation_missing_fields(self, vault_owner_client):
        resp = vault_owner_client.post(self.DONATION, json={"amount": 50})
        assert resp.status_code == 400

    def test_donation_below_minimum(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.DONATION,
            json={"amount": 10, "payment_method": "crypto"},
        )
        assert resp.status_code == 400


class TestPaymentVaultModel:
    @staticmethod
    def _vault():
        from models.payment_vault import PaymentVault

        vault = PaymentVault()
        vault.set_vault_password("secret")
        vault.max_failed_attempts = 3
        vault.failed_attempts = 0
        return vault

    def test_get_tenant_vault_none_for_null_tenant(self):
        from models.payment_vault import PaymentVault

        assert PaymentVault.get_tenant_vault(None) is None

    def test_get_platform_and_tenant_vault_query(self, mocker):
        from models.payment_vault import PaymentVault

        mock_q = MagicMock()
        mock_q.filter.return_value.order_by.return_value.first.return_value = MagicMock(
            id=1
        )
        mocker.patch.object(PaymentVault, "query", mock_q)
        assert PaymentVault.get_platform_vault().id == 1

        mock_q.filter_by.return_value.order_by.return_value.first.return_value = (
            MagicMock(id=2)
        )
        assert PaymentVault.get_tenant_vault(5).id == 2

    def test_check_vault_password(self):
        vault = self._vault()
        assert vault.check_vault_password("secret") is True
        assert vault.check_vault_password("wrong") is False

    def test_unlock_vault_success(self, mocker):
        vault = self._vault()
        mock_session = mocker.patch("models.payment_vault.db.session")
        assert vault.unlock_vault("secret") is True
        assert vault.is_locked is False
        assert vault.failed_attempts == 0
        mock_session.flush.assert_called()

    def test_unlock_vault_failure_increments_attempts(self, mocker):
        vault = self._vault()
        mock_session = mocker.patch("models.payment_vault.db.session")
        assert vault.unlock_vault("bad") is False
        assert vault.failed_attempts == 1
        mock_session.flush.assert_called()

    def test_lock_and_reset_failed_attempts(self, mocker):
        vault = self._vault()
        mock_session = mocker.patch("models.payment_vault.db.session")
        vault.lock_vault()
        assert vault.is_locked is True
        vault.reset_failed_attempts()
        assert vault.failed_attempts == 0
        assert mock_session.flush.call_count >= 2

    def test_is_vault_accessible_locked(self):
        vault = self._vault()
        vault.is_locked = True
        assert vault.is_vault_accessible() is False

    def test_is_vault_accessible_auto_lock(self, mocker):
        from datetime import datetime, timedelta, timezone

        vault = self._vault()
        vault.is_locked = False
        vault.auto_lock_minutes = 5
        vault.last_access = datetime.now(timezone.utc) - timedelta(minutes=10)
        mock_session = mocker.patch("models.payment_vault.db.session")
        assert vault.is_vault_accessible() is False
        assert vault.is_locked is True
        mock_session.flush.assert_called()

    def test_is_vault_accessible_when_unlocked_and_fresh(self):
        from datetime import datetime, timezone

        vault = self._vault()
        vault.is_locked = False
        vault.auto_lock_minutes = 30
        vault.last_access = datetime.now(timezone.utc)
        assert vault.is_vault_accessible() is True

    def test_payment_log_action(self, mocker):
        from models.payment_vault import PaymentLog

        mock_session = mocker.patch("models.payment_vault.db.session")
        log = PaymentLog.log_action(
            vault_id=1,
            action="unlock",
            description="vault opened",
            transaction_id="TX-9",
            amount=10,
        )
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        assert log.action == "unlock"

        vault = self._vault()
        vault.failed_attempts = 3
        assert vault.is_locked_out() is True

    def test_payment_transaction_to_dict(self):
        from datetime import datetime
        from decimal import Decimal
        from models.payment_vault import PaymentTransaction

        tx = PaymentTransaction(
            transaction_id="TX-1",
            amount_usd=Decimal("50"),
            amount_crypto=Decimal("0.001"),
            crypto_currency="BTC",
            created_at=datetime(2025, 1, 1),
        )
        data = tx.to_dict()
        assert data["transaction_id"] == "TX-1"
        assert data["amount_usd"] == 50.0
        assert data["amount_crypto"] == 0.001
