"""Gap100 for routes/payment_vault.py lines 1256->1273.

Covers crypto-success branch (1256-1265) and bank else branch (1266-1271)
plus the donation lookup line 1273 via API /api/purchase.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_db(mock_db):
    pass


@pytest.fixture(autouse=True)
def _patch_render(mocker):
    mocker.patch("routes.payment_vault.render_template", return_value="ok")


@pytest.fixture
def trusted_client(app_factory, bypass_owner_auth):
    from routes.payment_vault import payment_vault_bp

    app = app_factory(
        payment_vault_bp,
        config_overrides={"PAYMENT_VAULT_TRUSTED_ORIGINS": ["http://localhost:5000"]},
    )
    return app.test_client()


def _write_api_key(mocker, scope="write"):
    key = MagicMock()
    key.scope = scope
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


def _active_package(mocker, price=50):
    pkg = MagicMock()
    pkg.is_active = True
    pkg.price = price
    pkg.name_ar = "Basic"
    pkg.slug = "basic"
    mocker.patch(
        "routes.payment_vault.VaultQueryService.get_package_by_id",
        return_value=pkg,
    )
    return pkg


class TestApiPurchaseCryptoSuccess:
    """Lines 1256-1265: crypto payment success assigns transaction_id and payment_details."""

    def test_crypto_success_sets_transaction_and_details(self, trusted_client, mocker):
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        _active_package(mocker)
        mocker.patch(
            "routes.payment_vault.VaultQueryService.find_donation_by_transaction_hash",
            return_value=None,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        svc = MagicMock()
        svc.create_payment.return_value = {
            "success": True,
            "payment_id": "np_123",
            "pay_address": "addr_abc",
            "pay_amount": 0.002,
            "invoice_url": "https://nowpayments.io/invoice/123",
        }
        mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)

        resp = trusted_client.post(
            "/payment-vault/api/purchase",
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "crypto",
                "amount_paid": 100,
                "crypto_currency": "btc",
            },
            headers={
                "Idempotency-Key": "crypto-success-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        # payment_details path covered, response includes payment fields
        assert body["data"]["payment_address"] == "addr_abc"
        assert body["data"]["payment_amount"] == 0.002
        assert body["data"]["crypto_currency"] == "BTC"
        assert body["data"]["payment_id"] == "np_123"
        svc.create_payment.assert_called_once()


class TestApiPurchaseCryptoFailure:
    """Crypto method but NOWPayments returns failure: covers fallthrough without 1256 block."""

    def test_crypto_failure_no_transaction_update(self, trusted_client, mocker):
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        _active_package(mocker)
        mocker.patch(
            "routes.payment_vault.VaultQueryService.find_donation_by_transaction_hash",
            return_value=None,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        svc = MagicMock()
        svc.create_payment.return_value = {"success": False}
        mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)

        resp = trusted_client.post(
            "/payment-vault/api/purchase",
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "crypto",
                "amount_paid": 100,
            },
            headers={
                "Idempotency-Key": "crypto-fail-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        # no crypto fields when success false
        assert "payment_address" not in body["data"]


class TestApiPurchaseBankElse:
    """Lines 1266-1271: bank method hits else block setting original_method bank note."""

    def test_bank_method_sets_bank_note(self, trusted_client, mocker):
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        _active_package(mocker)
        mocker.patch(
            "routes.payment_vault.VaultQueryService.find_donation_by_transaction_hash",
            return_value=None,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")

        resp = trusted_client.post(
            "/payment-vault/api/purchase",
            json={
                "package_id": 1,
                "customer_name": "Ali",
                "customer_email": "ali@test.com",
                "payment_method": "bank",
                "amount_paid": 100,
            },
            headers={
                "Idempotency-Key": "bank-gap-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True


class TestApiPurchaseDonationExists:
    """Line 1273: donation already exists skips creation."""

    def test_existing_donation_skips_insert(self, trusted_client, mocker):
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        _active_package(mocker)
        existing = MagicMock()
        mocker.patch(
            "routes.payment_vault.VaultQueryService.find_donation_by_transaction_hash",
            return_value=existing,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        svc = MagicMock()
        svc.create_payment.return_value = {
            "success": True,
            "payment_id": "np_exists",
            "pay_address": "addr_x",
            "pay_amount": 1.0,
            "invoice_url": "https://nowpayments.io/invoice/x",
        }
        mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)

        resp = trusted_client.post(
            "/payment-vault/api/purchase",
            json={
                "package_id": 1,
                "customer_name": "Sara",
                "customer_email": "sara@test.com",
                "payment_method": "crypto",
                "amount_paid": 200,
            },
            headers={
                "Idempotency-Key": "don-exists-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True
