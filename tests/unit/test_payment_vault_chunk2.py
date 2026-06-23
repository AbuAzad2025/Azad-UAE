"""tests/unit/test_payment_vault_chunk2.py — Webhook replay protection,
Idempotency-Key caching, X-API-Key scoping, and signature validation."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from decimal import Decimal

import pytest


# =============================================================================
# _reject_stale_webhook_timestamp
# =============================================================================

class TestReplayProtection:
    """Direct tests for the `_reject_stale_webhook_timestamp` helper."""

    def test_valid_recent_timestamp_returns_none(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        now = datetime.now(timezone.utc)
        payload = {"timestamp": now.isoformat(), "payment_id": "123"}
        with app.app_context():
            result = _reject_stale_webhook_timestamp(payload)
        assert result is None

    def test_stale_timestamp_older_than_5min_returns_401(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        payload = {"timestamp": old.isoformat(), "payment_id": "123"}
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp(payload)
        assert code == 401
        assert "stale" in resp.get_json()["error"].lower()

    def test_future_timestamp_returns_401(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {"timestamp": future.isoformat()}
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp(payload)
        assert code == 401

    def test_numeric_timestamp_accepted(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        now_ts = datetime.now(timezone.utc).timestamp()
        payload = {"timestamp": now_ts}
        with app.app_context():
            result = _reject_stale_webhook_timestamp(payload)
        assert result is None

    def test_missing_timestamp_graceful_degradation(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        payload = {"payment_id": "123"}
        with app.app_context():
            result = _reject_stale_webhook_timestamp(payload)
        assert result is None

    def test_created_at_fallback(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        payload = {"created_at": old.isoformat()}
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp(payload)
        assert code == 401


# =============================================================================
# _check_idempotency_key / _save_idempotency_key
# =============================================================================

class TestIdempotencyKey:
    """Idempotency-Key cache behaviour."""

    def _reset_store(self):
        from routes.payment_vault import _idempotency_store
        _idempotency_store.clear()

    def test_cache_miss_returns_none(self, app_factory, mocker):
        from flask import request
        from routes.payment_vault import payment_vault_bp, _check_idempotency_key

        app = app_factory(payment_vault_bp)
        self._reset_store()
        with app.test_request_context(
            headers={"Idempotency-Key": "key-001"},
        ):
            result = _check_idempotency_key()
        assert result is None

    def test_cache_hit_returns_cached_response(self, app_factory, mocker):
        from flask import request
        from routes.payment_vault import (
            payment_vault_bp, _check_idempotency_key, _save_idempotency_key,
        )

        app = app_factory(payment_vault_bp)
        self._reset_store()
        with app.test_request_context(
            headers={"Idempotency-Key": "key-001"},
        ):
            _save_idempotency_key({"success": True}, 201)
            resp, code = _check_idempotency_key()
        assert code == 201
        assert resp.get_json()["success"] is True

    def test_no_key_header_returns_none(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _check_idempotency_key

        app = app_factory(payment_vault_bp)
        self._reset_store()
        with app.test_request_context():
            result = _check_idempotency_key()
        assert result is None

    def test_different_keys_independent(self, app_factory, mocker):
        from routes.payment_vault import (
            payment_vault_bp, _check_idempotency_key, _save_idempotency_key,
        )

        app = app_factory(payment_vault_bp)
        self._reset_store()
        with app.test_request_context(
            headers={"Idempotency-Key": "key-A"},
        ):
            _save_idempotency_key({"id": "A"}, 201)
        with app.test_request_context(
            headers={"Idempotency-Key": "key-B"},
        ):
            result = _check_idempotency_key()
        assert result is None  # key-B is not cached


# =============================================================================
# _validate_api_key
# =============================================================================

class TestApiKeyValidation:
    """X-API-Key scope enforcement."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from routes.payment_vault import _idempotency_store
        _idempotency_store.clear()

    def test_missing_key_returns_401(self, app_factory, mock_db, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_api_key

        app = app_factory(payment_vault_bp)
        with app.test_request_context():
            resp, code = _validate_api_key(required_scope='write')
        assert code == 401
        assert "API key" in resp.get_json()["error"]

    def test_invalid_key_returns_403(self, app_factory, mock_db, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_api_key

        app = app_factory(payment_vault_bp)

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        mocker.patch("models.api_key.APIKey.query", mock_query)

        with app.test_request_context(
            headers={"X-API-Key": "bad-key"},
        ):
            resp, code = _validate_api_key(required_scope='write')
        assert code == 403
        assert "Invalid" in resp.get_json()["error"]

    def test_read_only_key_blocked_on_write(self, app_factory, mock_db, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_api_key

        app = app_factory(payment_vault_bp)
        mock_key = MagicMock()
        mock_key.scope = 'read'
        mock_key.key = 'read-key'
        mock_key.last_used = None
        mock_key.usage_count = 0

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_key
        mocker.patch("models.api_key.APIKey.query", mock_query)

        with app.test_request_context(
            headers={"X-API-Key": "read-key"},
        ):
            resp, code = _validate_api_key(required_scope='write')
        assert code == 403
        assert "Read-only" in resp.get_json()["error"]

    def test_valid_write_key_passes(self, app_factory, mock_db, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_api_key

        app = app_factory(payment_vault_bp)
        mock_key = MagicMock()
        mock_key.scope = 'write'
        mock_key.key = 'write-key'
        mock_key.last_used = None
        mock_key.usage_count = 0

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_key
        mocker.patch("models.api_key.APIKey.query", mock_query)

        with app.test_request_context(
            headers={"X-API-Key": "write-key"},
        ):
            result = _validate_api_key(required_scope='write')
        assert result is None


# =============================================================================
# Webhook endpoint — signature validation integration
# =============================================================================

class TestWebhookSignatureValidation:
    """NOWPayments webhook endpoint signature checks."""

    PAYLOAD = b'{"payment_id":"p123","payment_status":"finished"}'

    @pytest.fixture(autouse=True)
    def _patch_common(self, mocker, mock_db):
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=MagicMock(nowpayments_ipn_secret="sec"))
        mocker.patch("utils.nowpayments_ipn.resolve_nowpayments_ipn_secret", return_value="sec")
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        mocker.patch("routes.payment_vault._reject_stale_webhook_timestamp", return_value=None)

    def test_valid_signature_returns_200(self, vault_owner_client, mocker):
        mocker.patch(
            "services.webhook_service.WebhookService.verify_nowpayments_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_nowpayments_webhook",
            return_value={"success": True},
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"x-nowpayments-sig": "valid-sig"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_missing_signature_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.PAYLOAD,
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_signature_returns_403(self, vault_owner_client, mocker):
        mocker.patch(
            "services.webhook_service.WebhookService.verify_nowpayments_signature",
            return_value=False,
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"x-nowpayments-sig": "bad-sig"},
        )
        assert resp.status_code == 403

    def test_missing_ipn_secret_returns_503(self, vault_owner_client, mocker):
        mocker.patch("utils.nowpayments_ipn.resolve_nowpayments_ipn_secret", return_value=None)
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"x-nowpayments-sig": "some-sig"},
        )
        assert resp.status_code == 503


# =============================================================================
# Public API endpoints — idempotency + API-key integration
# =============================================================================

class TestPurchaseEndpointIdempotency:
    """/api/purchase honours Idempotency-Key and X-API-Key."""

    ENDPOINT = "/payment-vault/api/purchase"
    SAMPLE_DATA = {
        "package_id": 1, "customer_name": "Ali",
        "customer_email": "ali@test.com", "payment_method": "bank",
        "amount_paid": 100,
    }

    @pytest.fixture(autouse=True)
    def _patch_deps(self, mocker, mock_db):
        mocker.patch("routes.payment_vault._validate_public_api_origin", return_value=None)
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        mocker.patch("routes.payment_vault._check_idempotency_key", return_value=None)
        mock_pkg_cls = mocker.patch("routes.payment_vault.Package")
        self.mock_pkg = MagicMock()
        self.mock_pkg.id = 1
        self.mock_pkg.is_active = True
        self.mock_pkg.price = 50
        self.mock_pkg.name_ar = "Basic"
        self.mock_pkg.slug = "basic"
        mock_pkg_cls.query.get.return_value = self.mock_pkg
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        mocker.patch("routes.payment_vault.Donation.query.filter_by", return_value=MagicMock(first=MagicMock(return_value=None)))

    def test_first_call_with_key_creates_and_caches(self, vault_owner_client, mocker):
        save_spy = mocker.patch("routes.payment_vault._save_idempotency_key")
        mocker.patch("routes.payment_vault.NOWPaymentsService")

        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"Idempotency-Key": "purchase-1", "X-API-Key": "write-key"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True
        save_spy.assert_called_once()

    def test_second_call_with_same_key_returns_cached(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault._check_idempotency_key",
            return_value=({"cached": True}, 200),
        )
        spy = mocker.patch("routes.payment_vault.api_create_purchase")

        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"Idempotency-Key": "purchase-1", "X-API-Key": "write-key"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["cached"] is True
        spy.assert_not_called()

    def test_missing_idempotency_key_processes_normally(self, vault_owner_client, mocker):
        mocker.patch("routes.payment_vault.NOWPaymentsService")

        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"X-API-Key": "write-key"},
        )
        assert resp.status_code == 201

    def test_missing_api_key_returns_401(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault._validate_api_key",
            return_value=({"success": False, "error": "API key is required"}, 401),
        )
        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
        )
        assert resp.status_code == 401


class TestDonationEndpointSecurity:
    """/api/donation honours Idempotency-Key and X-API-Key."""

    ENDPOINT = "/payment-vault/api/donation"
    SAMPLE_DATA = {"amount": 50, "payment_method": "crypto", "crypto_type": "btc"}

    @pytest.fixture(autouse=True)
    def _patch_deps(self, mocker, mock_db):
        mocker.patch("routes.payment_vault._validate_public_api_origin", return_value=None)
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        mocker.patch("routes.payment_vault._check_idempotency_key", return_value=None)
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")

        mock_nowpayments = mocker.patch("routes.payment_vault.NOWPaymentsService")
        mock_nowpayments.return_value.create_payment.return_value = {"success": True, "pay_address": "abc"}

    def test_donation_with_valid_key_creates(self, vault_owner_client, mocker):
        save_spy = mocker.patch("routes.payment_vault._save_idempotency_key")

        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"Idempotency-Key": "don-1", "X-API-Key": "write-key"},
        )
        assert resp.status_code == 201
        save_spy.assert_called_once()

    def test_donation_readonly_key_blocked(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault._validate_api_key",
            return_value=({"success": False, "error": "Read-only API key cannot perform this action"}, 403),
        )
        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"X-API-Key": "read-key"},
        )
        assert resp.status_code == 403
        assert "Read-only" in resp.get_json()["error"]

    def test_donation_replay_via_cache(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault._check_idempotency_key",
            return_value=({"cached": True}, 200),
        )
        spy = mocker.patch("routes.payment_vault.api_create_donation")

        resp = vault_owner_client.post(
            self.ENDPOINT, json=self.SAMPLE_DATA,
            headers={"Idempotency-Key": "don-1", "X-API-Key": "write-key"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["cached"] is True
        spy.assert_not_called()


# =============================================================================
# API Key model — scope column
# =============================================================================

class TestApiKeyModel:
    """Verify the APIKey model has a scope column."""

    def test_scope_column_exists(self):
        from models import APIKey
        col = getattr(APIKey, 'scope', None)
        assert col is not None
        assert hasattr(col, 'type')

    def test_scope_defaults_to_write(self):
        from models import APIKey
        col = getattr(APIKey, 'scope', None)
        assert col is not None
        default = col.default.arg if col.default else 'write'
        assert default == 'write'
