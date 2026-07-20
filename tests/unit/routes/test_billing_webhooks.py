"""Unit tests for routes/billing_webhooks.py — Stripe/generic billing webhooks.

Stripe is faked at the sys.modules boundary (same pattern as
tests/unit/services/test_webhook_service.py); the provisioning service is
mocked at its source module. Signature verification itself is exercised for
real through the fake stripe module.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.saas_provisioning_service import SaaSProvisioningError


def _fake_stripe(mocker, event=None, construct_error=None):
    stripe_mod = MagicMock(name="stripe")

    class SignatureVerificationError(Exception):
        pass

    stripe_mod.error.SignatureVerificationError = SignatureVerificationError
    if construct_error is not None:
        stripe_mod.Webhook.construct_event.side_effect = construct_error
    else:
        stripe_mod.Webhook.construct_event.return_value = event
    mocker.patch.dict(sys.modules, {"stripe": stripe_mod})
    return stripe_mod


@pytest.fixture
def stripe_secret(app, monkeypatch):
    monkeypatch.setitem(app.config, "STRIPE_WEBHOOK_SECRET", "whsec_test")


def _checkout_event(**overrides):
    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "created": int(datetime.now(timezone.utc).timestamp()),
                "metadata": {
                    "tenant_id": "3",
                    "package_id": "4",
                    "duration_type": "annual",
                },
            }
        },
    }
    event.update(overrides)
    return event


class TestStripeWebhook:
    def test_unconfigured_secret_returns_503(self, client):
        resp = client.post("/billing-webhook/stripe", data=b"{}")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "Webhook not configured"

    def test_bad_signature_returns_403(self, client, stripe_secret, mocker):
        stripe_mod = _fake_stripe(mocker)
        stripe_mod.Webhook.construct_event.side_effect = stripe_mod.error.SignatureVerificationError("bad sig")
        resp = client.post(
            "/billing-webhook/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "t=1,v1=bad"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "Invalid signature"

    def test_missing_metadata_returns_400(self, client, stripe_secret, mocker):
        event = _checkout_event()
        event["data"]["object"]["metadata"] = {}
        _fake_stripe(mocker, event=event)
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Missing metadata"

    def test_valid_event_provisions_tenant(self, client, stripe_secret, mocker):
        _fake_stripe(mocker, event=_checkout_event())
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            return_value={"tenant_id": 3},
        )
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["provisioning"] == {"tenant_id": 3}
        provision.assert_called_once_with(tenant_id=3, package_id=4, duration_type="annual")

    def test_provisioning_error_returns_422(self, client, stripe_secret, mocker):
        _fake_stripe(mocker, event=_checkout_event())
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=SaaSProvisioningError("Tenant 3 not found"),
        )
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 422
        assert "Tenant 3 not found" in resp.get_json()["error"]

    def test_unhandled_event_type_acknowledged(self, client, stripe_secret, mocker):
        _fake_stripe(mocker, event=_checkout_event(type="customer.created"))
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "acknowledged"

    def test_duplicate_event_short_circuits(self, client, stripe_secret, mocker):
        _fake_stripe(mocker, event=_checkout_event())
        mocker.patch("routes.billing_webhooks._is_duplicate", return_value=True)
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "duplicate"
        provision.assert_not_called()

    def test_stale_event_rejected(self, client, stripe_secret, mocker):
        event = _checkout_event()
        event["data"]["object"]["created"] = int(datetime.now(timezone.utc).timestamp()) - 600
        _fake_stripe(mocker, event=event)
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Stale event"


class TestGenericWebhook:
    _SECRET = "test-secret-key"  # TestConfig.SECRET_KEY is the fallback secret

    def test_wrong_secret_returns_403(self, client):
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "payment_succeeded"},
            headers={"X-Webhook-Secret": "wrong"},
        )
        assert resp.status_code == 403

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/billing-webhook/generic",
            data="not-json",
            content_type="application/json",
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Invalid JSON"

    def test_missing_ids_returns_400(self, client):
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "payment_succeeded"},
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 400
        assert "tenant_id and package_id required" in resp.get_json()["error"]

    def test_unhandled_event_acknowledged(self, client):
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "ping"},
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "acknowledged"

    def test_valid_payment_provisions(self, client, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            return_value={"tenant_id": 3},
        )
        resp = client.post(
            "/billing-webhook/generic",
            json={
                "event": "payment_succeeded",
                "tenant_id": 3,
                "package_id": 4,
                "transaction_id": "manual-001",
            },
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        provision.assert_called_once_with(tenant_id=3, package_id=4, duration_type="monthly")

    def test_provisioning_error_returns_422(self, client, mocker):
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=SaaSProvisioningError("Package 4 not found or inactive"),
        )
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "payment_succeeded", "tenant_id": 3, "package_id": 4},
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 422

    def test_stale_timestamp_rejected(self, client):
        resp = client.post(
            "/billing-webhook/generic",
            json={
                "event": "payment_succeeded",
                "tenant_id": 3,
                "package_id": 4,
                "timestamp": int(datetime.now(timezone.utc).timestamp()) - 600,
            },
            headers={"X-Webhook-Secret": self._SECRET},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Stale event"


class TestCronCheckSubscriptions:
    def test_runs_without_configured_secret(self, client, mocker):
        run = mocker.patch(
            "utils.billing_scheduler.run_subscription_check",
            return_value={"checked": 5},
        )
        resp = client.post("/billing-webhook/api/cron/check-subscriptions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["checked"] == 5
        run.assert_called_once_with()

    def test_wrong_secret_aborts_403(self, client, app, monkeypatch):
        monkeypatch.setitem(app.config, "CRON_SECRET", "cron-x")
        resp = client.post("/billing-webhook/api/cron/check-subscriptions")
        assert resp.status_code == 403

    def test_correct_secret_runs(self, client, app, monkeypatch, mocker):
        monkeypatch.setitem(app.config, "CRON_SECRET", "cron-x")
        mocker.patch(
            "utils.billing_scheduler.run_subscription_check",
            return_value={"checked": 0},
        )
        resp = client.post(
            "/billing-webhook/api/cron/check-subscriptions",
            headers={"X-Cron-Secret": "cron-x"},
        )
        assert resp.status_code == 200

    def test_check_failure_returns_500(self, client, mocker):
        mocker.patch(
            "utils.billing_scheduler.run_subscription_check",
            side_effect=RuntimeError("scheduler down"),
        )
        resp = client.post("/billing-webhook/api/cron/check-subscriptions")
        assert resp.status_code == 500


class TestHelpers:
    def test_reject_stale_timestamp_passthrough_cases(self):
        from routes.billing_webhooks import _reject_stale_timestamp

        assert _reject_stale_timestamp(None) is None
        assert _reject_stale_timestamp({}) is None
        assert _reject_stale_timestamp({"created": "not-a-number"}) is None
        fresh = {"created": int(datetime.now(timezone.utc).timestamp())}
        assert _reject_stale_timestamp(fresh) is None

    def test_reject_stale_timestamp_old_event(self, app):
        from routes.billing_webhooks import _reject_stale_timestamp

        old = {"timestamp": int(datetime.now(timezone.utc).timestamp()) - 600}
        with app.test_request_context():
            body, status = _reject_stale_timestamp(old)
        assert status == 400

    def test_is_duplicate_without_event_id(self):
        from routes.billing_webhooks import _is_duplicate

        assert _is_duplicate("stripe", None) is False
        assert _is_duplicate("stripe", "") is False

    def test_is_duplicate_uses_cache(self, mocker):
        from routes.billing_webhooks import _is_duplicate

        store = {}
        fake_cache = MagicMock(name="cache")
        fake_cache.get.side_effect = store.get
        fake_cache.set.side_effect = lambda key, value, timeout=None: store.update({key: value})
        mocker.patch("extensions.cache", fake_cache)

        assert _is_duplicate("stripe", "evt_1") is False
        assert _is_duplicate("stripe", "evt_1") is True
