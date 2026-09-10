"""Coverage tests (part A) for routes/payment_vault.py gaps.

Targets (real response paths via test client; mocks only at DB/external
boundaries — VaultQueryService, IdempotencyService, NOWPaymentsService,
LoggingCore, render_template):
  lines 205, 688-689, 782-787, 877-878, 936, 945
  arcs 211->213, 714->716, 716->718, 1256->1273
"""

from __future__ import annotations

import datetime as _dt_mod
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


class TestIdempotencyMissingEndpoint:
    def test_endpoint_context_missing_returns_500(self, app_factory):
        """Line 205: no endpoint context -> 500."""
        from routes.payment_vault import _check_idempotency_key, payment_vault_bp

        app = app_factory(payment_vault_bp)
        with app.test_request_context("/", headers={"Idempotency-Key": "k-ctx"}):
            resp, code = _check_idempotency_key(endpoint=None)
        assert code == 500
        assert "endpoint" in resp.get_json()["message"].lower()


class TestCreatePackageNumberParsing:
    def test_bad_numbers_default_with_explicit_limits(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 688-689 + arcs 714->716, 716->718.

        price/sort_order unparsable -> _as_float/_as_int defaults;
        explicit max_users/max_branches skip the None-defaults.
        """
        mocker.patch(
            "routes.payment_vault.VaultQueryService.find_package_by_slug",
            return_value=None,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/package/create",
            data={
                "name_ar": "باقة",
                "name_en": "Plan",
                "price": "not-a-number",
                "sort_order": "bad",
                "support_duration_months": "bad",
                "max_users": "5",
                "max_branches": "3",
            },
        )
        assert resp.status_code == 302


class TestEditPackageIntParsing:
    def _pkg(self):
        from decimal import Decimal

        pkg = MagicMock()
        pkg.name_ar = "باقة"
        pkg.name_en = "Plan"
        pkg.price = Decimal("10")
        pkg.support_duration_months = 3
        return pkg

    def test_blank_support_months_keeps_default(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 782-784: blank -> int(default)."""
        pkg = self._pkg()
        mocker.patch(
            "routes.payment_vault.VaultQueryService.get_package_or_404",
            return_value=pkg,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/package/1/edit",
            data={"name_ar": "باقة", "support_duration_months": ""},
        )
        assert resp.status_code == 302

    def test_invalid_support_months_falls_back(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 782-783/785-787: garbage -> except -> int(default)."""
        pkg = self._pkg()
        mocker.patch(
            "routes.payment_vault.VaultQueryService.get_package_or_404",
            return_value=pkg,
        )
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/package/1/edit",
            data={"name_ar": "باقة", "support_duration_months": "not-an-int!!!"},
        )
        assert resp.status_code == 302


class TestReportsYearWrap:
    def test_january_window_wraps_into_prior_year(self, vault_owner_client, unlocked_vault, mocker):
        """Lines 877-878: month arithmetic wraps below January."""

        class _JanClock(_dt_mod.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 15, 12, 0, 0)

        mocker.patch("routes.payment_vault.datetime", _JanClock)
        mocker.patch(
            "routes.payment_vault.VaultQueryService.list_platform_records_desc",
            return_value=[],
        )
        mocker.patch(
            "routes.payment_vault.VaultQueryService.donation_monthly_aggregates",
            return_value=[],
        )
        mocker.patch(
            "routes.payment_vault.VaultQueryService.platform_package_purchase_counts",
            return_value={},
        )
        resp = vault_owner_client.get("/payment-vault/reports")
        assert resp.status_code == 200


class TestLockVaultJson:
    def test_locked_json_returns_vault_locked_flag(self, vault_owner_client, unlocked_vault, mocker):
        """Line 936: unlocked vault + JSON accept -> 200 flag payload."""
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/lock", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        assert resp.get_json()["vault_locked"] is True

    def test_no_vault_json_returns_404(self, vault_owner_client, mocker):
        """Line 945: missing vault + JSON accept -> 404."""
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=None,
        )
        resp = vault_owner_client.post("/payment-vault/lock", headers={"Accept": "application/json"})
        assert resp.status_code == 404


class TestApiPurchaseBankPath:
    def test_bank_method_skips_crypto(self, trusted_client, mocker):
        """Arcs 211->213 (explicit payload) and 1256->1273 (bank path)."""
        _write_api_key(mocker)
        _fresh_idempotency(mocker)
        pkg = MagicMock()
        pkg.is_active = True
        pkg.price = 50
        pkg.name_ar = "Basic"
        pkg.slug = "basic"
        mocker.patch(
            "routes.payment_vault.VaultQueryService.get_package_by_id",
            return_value=pkg,
        )
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
                "Idempotency-Key": "bank-1",
                "X-API-Key": "write-key",
                "Origin": "http://localhost:5000",
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True
