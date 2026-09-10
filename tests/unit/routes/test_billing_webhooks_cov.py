"""Coverage for routes/billing_webhooks.py uncovered lines/arcs.

Targets:
- lines 50-51 (_is_duplicate dedup-cache error path)
- lines 124-126 (stripe_webhook outer except -> 500)
- lines 157-158 (generic_webhook secret not configured -> 503)
- line 177 (generic_webhook duplicate short-circuit)
- lines 211-213 (generic_webhook outer except -> 500)

Every test drives the route via the test client with mocked services and
asserts the real response path taken.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from services.saas_provisioning_service import SaaSProvisioningError


def _cov_fake_stripe(mocker, event=None, construct_error=None):
    stripe_mod = MagicMock(name="stripe")
    stripe_mod.error.SignatureVerificationError = type("SignatureVerificationError", (Exception,), {})
    if construct_error is not None:
        stripe_mod.Webhook.construct_event.side_effect = construct_error
    else:
        stripe_mod.Webhook.construct_event.return_value = event
    mocker.patch.dict(sys.modules, {"stripe": stripe_mod})
    return stripe_mod


def _cov_checkout_event(**overrides):
    event = {
        "id": "evt_cov_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "created": int(datetime.now(UTC).timestamp()),
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


@pytest.fixture
def cov_stripe_secret(app, monkeypatch):
    monkeypatch.setitem(app.config, "STRIPE_WEBHOOK_SECRET", "whsec_test")


class TestGenericWebhookDedupCacheError:
    def test_cache_failure_falls_through_lines_50_51(self, client, app, mocker):
        """Lines 50-51: cache error inside _is_duplicate logs and returns False."""
        app.config["BILLING_WEBHOOK_SECRET"] = "cov-secret"
        mocker.patch("extensions.cache.get", side_effect=RuntimeError("redis down"))
        mocker.patch("extensions.cache.set", side_effect=RuntimeError("redis down"))
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
                "transaction_id": "cov-tx-001",
            },
            headers={"X-Webhook-Secret": "cov-secret"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        provision.assert_called_once_with(tenant_id=3, package_id=4, duration_type="monthly")


class TestStripeWebhookOuterExcept:
    def test_unexpected_error_returns_500_lines_124_126(self, client, cov_stripe_secret, mocker):
        """Lines 124-126: unexpected failure inside stripe handler -> 500."""
        _cov_fake_stripe(mocker, event=_cov_checkout_event())
        mocker.patch(
            "routes.billing_webhooks._is_duplicate",
            side_effect=RuntimeError("dedup crashed"),
        )
        resp = client.post("/billing-webhook/stripe", data=b"payload")
        assert resp.status_code == 500
        assert resp.get_json()["message"] == "Webhook processing failed"


class TestGenericWebhookSecretMissing:
    def test_secret_not_configured_lines_157_158(self, client, app):
        """Lines 157-158: missing BILLING_WEBHOOK_SECRET -> 503."""
        app.config["BILLING_WEBHOOK_SECRET"] = None
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "payment_succeeded", "tenant_id": 1, "package_id": 2},
            headers={"X-Webhook-Secret": "anything"},
        )
        assert resp.status_code == 503
        assert resp.get_json()["message"] == "Webhook not configured"


class TestGenericWebhookDuplicate:
    def test_duplicate_short_circuit_line_177(self, client, app, mocker):
        """Line 177: duplicate generic event returns duplicate status."""
        app.config["BILLING_WEBHOOK_SECRET"] = "cov-secret"
        mocker.patch("routes.billing_webhooks._is_duplicate", return_value=True)
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = client.post(
            "/billing-webhook/generic",
            json={
                "event": "payment_succeeded",
                "tenant_id": 3,
                "package_id": 4,
                "transaction_id": "cov-dup-001",
            },
            headers={"X-Webhook-Secret": "cov-secret"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "duplicate"
        provision.assert_not_called()


class TestGenericWebhookOuterExcept:
    def test_unexpected_error_returns_500_lines_211_213(self, client, app, mocker):
        """Lines 211-213: non-provisioning failure in generic handler -> 500."""
        app.config["BILLING_WEBHOOK_SECRET"] = "cov-secret"
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=RuntimeError("db down"),
        )
        resp = client.post(
            "/billing-webhook/generic",
            json={
                "event": "payment_succeeded",
                "tenant_id": 3,
                "package_id": 4,
                "transaction_id": "cov-err-001",
            },
            headers={"X-Webhook-Secret": "cov-secret"},
        )
        assert resp.status_code == 500
        assert resp.get_json()["message"] == "Webhook processing failed"

    def test_provisioning_error_still_422_not_500(self, client, app, mocker):
        """Guard: SaaSProvisioningError stays 422 (adjacent branch, not 211-213)."""
        app.config["BILLING_WEBHOOK_SECRET"] = "cov-secret"
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=SaaSProvisioningError("Package 4 not found or inactive"),
        )
        resp = client.post(
            "/billing-webhook/generic",
            json={"event": "payment_succeeded", "tenant_id": 3, "package_id": 4},
            headers={"X-Webhook-Secret": "cov-secret"},
        )
        assert resp.status_code == 422
