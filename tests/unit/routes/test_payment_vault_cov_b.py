"""Coverage tests (part B) for routes/payment_vault.py gaps.

Targets (real response paths via test client; mocks only at DB/external
boundaries — VaultQueryService, IdempotencyService, NOWPaymentsService,
AzadPlatformFeeService, WebhookService, mail, LoggingCore, render_template):
  lines 1207-1208, 1509-1538, 1687-1688, 1691-1692, 1699-1700, 1702-1703,
        1723, 1728, 1737-1764
  arcs 1372->1375, 1959->1970, 2009->2019
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_db(mock_db):
    pass


@pytest.fixture
def unlocked_vault(mocker):
    vault = MagicMock()
    vault.id = 1
    vault.is_locked = False
    mocker.patch(
        "routes.payment_vault._get_vault_for_current_tenant",
        return_value=vault,
    )
    return vault


@pytest.fixture(autouse=True)
def _patch_render(mocker):
    mocker.patch("routes.payment_vault.render_template", return_value="ok")


@pytest.fixture
def trusted_client(app_factory, bypass_owner_auth):
    """Owner client with a real public-API origin allowlist (no helper mocks)."""
    from routes.payment_vault import payment_vault_bp

    app = app_factory(
        payment_vault_bp,
        config_overrides={"PAYMENT_VAULT_TRUSTED_ORIGINS": ["http://localhost:5000"]},
    )
    return app.test_client()


def _write_api_key(mocker):
    key = MagicMock()
    key.scope = "write"
    key.tenant_id = 1
    key.created_by = 9
    key.id = 7
    mocker.patch(
        "routes.payment_vault.VaultQueryService.find_active_api_key",
        return_value=key,
    )
    return key


def _fresh_idempotency(mocker):
    record = MagicMock()
    mocker.patch(
        "routes.payment_vault.IdempotencyService.begin",
        return_value=(record, None),
    )
    mocker.patch("routes.payment_vault.IdempotencyService.complete")
    return record


def _active_package(mocker):
    pkg = MagicMock()
    pkg.is_active = True
    pkg.price = 50
    pkg.name_ar = "Basic"
    pkg.slug = "basic"
    mocker.patch(
        "routes.payment_vault.VaultQueryService.get_package_by_id",
        return_value=pkg,
    )
    return pkg


class TestApiPurchaseInvalidAmount:
    def test_unparsable_amount_paid_returns_400(self, trusted_client, mocker):
        """Lines 1207-1208: Decimal() guard rejects garbage amounts."""
        _write_api_key(mocker)
        _active_package(mocker)
        resp = trusted_client.post(
            "/payment-vault/api/purchase",
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "bank",
                "amount_paid": "not-a-number!!!",
            },
            headers={
                "Idempotency-Key": "bad-amount-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 400


class TestApiDonationValidEmail:
    def test_valid_donor_email_kept(self, trusted_client, mocker):
        """Arc 1372->1375: well-formed donor email survives sanitization."""
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        svc = MagicMock()
        svc.create_payment.return_value = {
            "success": True,
            "payment_id": "np_d1",
            "pay_address": "addr1",
            "pay_amount": 50.0,
            "invoice_url": "https://nowpayments.io/invoice/d1",
        }
        mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = trusted_client.post(
            "/payment-vault/api/donation",
            json={
                "amount": 50,
                "payment_method": "crypto",
                "donor_name": "Sara",
                "donor_email": "sara@example.com",
                "crypto_type": "btc",
            },
            headers={
                "Idempotency-Key": "don-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["payment_address"] == "addr1"


def _purchase_with_email(mocker, email="buyer@test.com"):
    purchase = MagicMock()
    purchase.id = 3
    purchase.customer_email = email
    purchase.customer_name = "Buyer"
    purchase.amount_paid = 100
    purchase.currency = "USD"
    purchase.payment_status = "completed"
    pkg = MagicMock()
    pkg.name_ar = "الباقة"
    pkg.name_en = "Plan"
    purchase.package = pkg
    mocker.patch(
        "routes.payment_vault.VaultQueryService.get_purchase_or_404",
        return_value=purchase,
    )
    return purchase


class TestSendPurchaseEmail:
    def test_locked_vault_returns_403(self, vault_owner_client, mocker):
        """Line 1510-1511."""
        locked = MagicMock()
        locked.id = 1
        locked.is_locked = True
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=locked,
        )
        resp = vault_owner_client.post("/payment-vault/purchase/3/send-email")
        assert resp.status_code == 403

    def test_missing_customer_email_returns_400(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1514-1515."""
        _purchase_with_email(mocker, email=None)
        resp = vault_owner_client.post("/payment-vault/purchase/3/send-email")
        assert resp.status_code == 400

    def test_success_sends_receipt(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1517-1535: receipt mail is dispatched."""
        _purchase_with_email(mocker)
        mocker.patch("flask_mail.Message", return_value=MagicMock())
        send = mocker.patch("extensions.mail.send")
        resp = vault_owner_client.post("/payment-vault/purchase/3/send-email")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        send.assert_called_once()

    def test_mail_failure_returns_500(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1536-1538: SMTP errors surface as 500."""
        _purchase_with_email(mocker)
        mocker.patch("flask_mail.Message", return_value=MagicMock())
        mocker.patch("extensions.mail.send", side_effect=RuntimeError("smtp down"))
        resp = vault_owner_client.post("/payment-vault/purchase/3/send-email")
        assert resp.status_code == 500


class TestConfirmPlatformFees:
    def test_locked_vault_redirects(self, vault_owner_client, mocker):
        """Lines 1687-1688."""
        locked = MagicMock()
        locked.id = 1
        locked.is_locked = True
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=locked,
        )
        resp = vault_owner_client.post(
            "/payment-vault/platform-fees/confirm",
            data={"fee_ids": "1"},
        )
        assert resp.status_code == 302

    def test_json_without_fee_ids_warns(self, vault_owner_client, unlocked_vault):
        """Lines 1702-1703: empty selection redirects with a warning."""
        resp = vault_owner_client.post("/payment-vault/platform-fees/confirm", json={"fee_ids": []})
        assert resp.status_code == 302

    def test_json_null_fee_ids_treated_as_empty(self, vault_owner_client, unlocked_vault):
        """Lines 1699-1700: non-iterable fee_ids fall back to []."""
        resp = vault_owner_client.post("/payment-vault/platform-fees/confirm", json={"fee_ids": None})
        assert resp.status_code == 302

    def test_json_success_returns_result(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1691-1692 + 1723: JSON fee_ids confirmed as JSON."""
        confirm = mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.confirm_settlement_paid",
            return_value={"count": 2, "total_aed": 100},
        )
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/platform-fees/confirm", json={"fee_ids": [1, 2]})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        confirm.assert_called_once()

    def test_json_service_error_returns_400(self, vault_owner_client, unlocked_vault, mocker):
        """Line 1728: settlement failures surface as JSON 400."""
        mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.confirm_settlement_paid",
            side_effect=RuntimeError("boom"),
        )
        resp = vault_owner_client.post("/payment-vault/platform-fees/confirm", json={"fee_ids": [1]})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_form_fee_ids_redirect(self, vault_owner_client, unlocked_vault, mocker):
        """Form-encoded fee_ids confirm then redirect."""
        confirm = mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.confirm_settlement_paid",
            return_value={"count": 1, "total_aed": 50},
        )
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/platform-fees/confirm",
            data={"fee_ids": ["1", "2"]},
        )
        assert resp.status_code == 302
        confirm.assert_called_once()


def _donation_with_email(mocker, email="donor@test.com"):
    donation = MagicMock()
    donation.id = 5
    donation.donor_email = email
    donation.donor_name = "Donor"
    donation.amount_usd = 25
    mocker.patch(
        "routes.payment_vault.VaultQueryService.get_any_donation_or_404",
        return_value=donation,
    )
    return donation


class TestSendThankYou:
    def test_locked_vault_returns_403(self, vault_owner_client, mocker):
        """Lines 1737-1739."""
        locked = MagicMock()
        locked.id = 1
        locked.is_locked = True
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=locked,
        )
        resp = vault_owner_client.post("/payment-vault/donation/5/send-thank-you")
        assert resp.status_code == 403

    def test_missing_donor_email_returns_400(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1742-1743."""
        _donation_with_email(mocker, email=None)
        resp = vault_owner_client.post("/payment-vault/donation/5/send-thank-you")
        assert resp.status_code == 400

    def test_success_sends_thanks(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1745-1761: thank-you mail is dispatched."""
        _donation_with_email(mocker)
        mocker.patch("flask_mail.Message", return_value=MagicMock())
        send = mocker.patch("extensions.mail.send")
        resp = vault_owner_client.post("/payment-vault/donation/5/send-thank-you")
        assert resp.status_code == 200
        send.assert_called_once()

    def test_mail_failure_returns_500(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 1762-1764."""
        _donation_with_email(mocker)
        mocker.patch("flask_mail.Message", return_value=MagicMock())
        mocker.patch("extensions.mail.send", side_effect=RuntimeError("smtp down"))
        resp = vault_owner_client.post("/payment-vault/donation/5/send-thank-you")
        assert resp.status_code == 500


class TestWebhookVaultArcs:
    NOW_PAYLOAD = b'{"payment_id":"p-arcs","payment_status":"finished"}'

    def _now_common(self, mocker):
        mocker.patch(
            "routes.payment_vault._reject_stale_webhook_timestamp",
            return_value=None,
        )
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)

    def test_nowpayments_without_vault_skips_log(self, vault_owner_client, mocker):
        """Arc 1959->1970: no vault, no PaymentLog, still 200."""
        self._now_common(mocker)
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=None,
        )
        mocker.patch(
            "utils.nowpayments_ipn.resolve_nowpayments_ipn_secret",
            return_value="sec",
        )
        mocker.patch(
            "services.webhook_service.WebhookService.verify_nowpayments_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_nowpayments_webhook",
            return_value={"success": True},
        )
        log = mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.NOW_PAYLOAD,
            content_type="application/json",
            headers={"x-nowpayments-sig": "sig"},
        )
        assert resp.status_code == 200
        log.assert_not_called()

    def test_stripe_transient_vault_skips_log(self, vault_owner_client, mocker):
        """Arc 2009->2019: vault passes setup but is gone at log time."""
        mocker.patch(
            "routes.payment_vault._reject_stale_webhook_timestamp",
            return_value=None,
        )
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        vault = MagicMock()
        vault.stripe_webhook_secret = "whsec"
        vault.__bool__.side_effect = [True, False]
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=vault,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_stripe_webhook",
            return_value={"success": True},
        )
        log = mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=b'{"id":"evt-arcs","type":"payment_intent.succeeded"}',
            content_type="application/json",
            headers={"Stripe-Signature": "sig"},
        )
        assert resp.status_code == 200
        log.assert_not_called()
