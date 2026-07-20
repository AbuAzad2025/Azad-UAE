from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    vault.nowpayments_api_key = ""
    vault.nowpayments_ipn_secret = "sec"
    vault.stripe_webhook_secret = "whsec"
    mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=vault)
    mocker.patch("routes.payment_vault.PaymentVault.get_platform_vault", return_value=vault)
    return vault


@pytest.fixture
def mock_locked_vault(mocker):
    vault = MagicMock()
    vault.id = 1
    vault.is_locked = True
    vault.is_vault_accessible.return_value = False
    vault.unlock_vault.return_value = False
    vault.is_locked_out.return_value = False
    mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=vault)
    return vault


@pytest.fixture(autouse=True)
def _patch_render(mocker):
    mocker.patch("routes.payment_vault.render_template", return_value="ok")


@pytest.fixture
def mock_analytics(mocker):
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_daily_stats",
        return_value={"today_revenue": 0, "today_transactions": 0},
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_revenue_by_period",
        return_value={"labels": [], "purchases": [], "donations": []},
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_payment_method_stats",
        return_value={},
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_customer_behavior",
        return_value={},
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_package_performance",
        return_value={},
    )


class TestVaultSecurityHelpers:
    def test_is_production_env_true(self, app_factory, monkeypatch):
        from routes.payment_vault import payment_vault_bp, _is_production_env

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        app = app_factory(payment_vault_bp)
        with app.app_context():
            assert _is_production_env() is True

    def test_is_production_env_false_when_debug(self, app_factory, monkeypatch):
        from routes.payment_vault import payment_vault_bp, _is_production_env

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "1")
        app = app_factory(payment_vault_bp)
        with app.app_context():
            assert _is_production_env() is False

    def test_duplicate_webhook_no_event_id(self):
        from routes.payment_vault import _is_duplicate_webhook

        assert _is_duplicate_webhook("np", None) is False

    def test_duplicate_webhook_cache_hit(self, mocker):
        from routes.payment_vault import _is_duplicate_webhook

        cache = mocker.patch("extensions.cache")
        cache.get.return_value = "1"
        assert _is_duplicate_webhook("np", "evt-1") is True

    def test_duplicate_webhook_cache_miss_sets_key(self, mocker):
        from routes.payment_vault import _is_duplicate_webhook

        cache = mocker.patch("extensions.cache")
        cache.get.return_value = None
        assert _is_duplicate_webhook("np", "evt-2") is False
        cache.set.assert_called_once()

    def test_duplicate_webhook_cache_error(self, mocker):
        from extensions import cache as real_cache
        from routes.payment_vault import _is_duplicate_webhook

        mocker.patch.object(real_cache, "get", side_effect=RuntimeError("cache down"))
        assert _is_duplicate_webhook("np", "evt-cache-fail-unique") is False

    def test_trusted_origins_from_config(self, app_factory):
        from routes.payment_vault import (
            payment_vault_bp,
            _payment_vault_trusted_origins,
        )

        app = app_factory(
            payment_vault_bp,
            {"PAYMENT_VAULT_TRUSTED_ORIGINS": ["https://shop.example.com/"]},
        )
        with app.app_context():
            origins = _payment_vault_trusted_origins()
        assert "https://shop.example.com" in origins

    def test_trusted_origins_production_base_url(self, app_factory, monkeypatch):
        from routes.payment_vault import (
            payment_vault_bp,
            _payment_vault_trusted_origins,
        )

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        app = app_factory(payment_vault_bp, {"BASE_URL": "https://erp.example.com"})
        with app.app_context():
            origins = _payment_vault_trusted_origins()
        assert origins == frozenset({"https://erp.example.com"})

    def test_trusted_origins_dev_defaults(self, app_factory, monkeypatch):
        from routes.payment_vault import (
            payment_vault_bp,
            _payment_vault_trusted_origins,
            _DEV_VAULT_ORIGINS,
        )

        monkeypatch.setenv("APP_ENV", "development")
        app = app_factory(payment_vault_bp)
        with app.app_context():
            assert _payment_vault_trusted_origins() == _DEV_VAULT_ORIGINS

    def test_origin_from_referer_valid(self):
        from routes.payment_vault import _origin_from_referer

        assert _origin_from_referer("https://localhost:5000/path") == "https://localhost:5000"

    def test_origin_from_referer_invalid(self):
        from routes.payment_vault import _origin_from_referer

        assert _origin_from_referer("not-a-url") is None

    def test_validate_public_api_origin_no_trusted(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            "routes.payment_vault._payment_vault_trusted_origins",
            return_value=frozenset(),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context("/"):
            resp, code = _validate_public_api_origin()
        assert code == 503

    def test_validate_public_api_origin_bad_origin(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            "routes.payment_vault._payment_vault_trusted_origins",
            return_value=frozenset({"http://localhost:5000"}),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context("/", headers={"Origin": "https://evil.com"}):
            resp, code = _validate_public_api_origin()
        assert code == 403

    def test_validate_public_api_origin_good_referer(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            "routes.payment_vault._payment_vault_trusted_origins",
            return_value=frozenset({"http://localhost:5000"}),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context("/", headers={"Referer": "http://localhost:5000/pay"}):
            assert _validate_public_api_origin() is None

    def test_validate_public_api_origin_missing_headers(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            "routes.payment_vault._payment_vault_trusted_origins",
            return_value=frozenset({"http://localhost:5000"}),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context("/"):
            resp, code = _validate_public_api_origin()
        assert code == 403

    def test_reject_stale_webhook_none_data(self):
        from routes.payment_vault import _reject_stale_webhook_timestamp

        assert _reject_stale_webhook_timestamp(None) is None

    def test_reject_stale_webhook_old_timestamp(self, app_factory):
        from routes.payment_vault import (
            payment_vault_bp,
            _reject_stale_webhook_timestamp,
        )

        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        app = app_factory(payment_vault_bp)
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp({"timestamp": old})
        assert code == 401

    def test_reject_stale_webhook_future_timestamp(self, app_factory):
        from routes.payment_vault import (
            payment_vault_bp,
            _reject_stale_webhook_timestamp,
        )

        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        app = app_factory(payment_vault_bp)
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp({"timestamp": future})
        assert code == 401

    def test_reject_stale_webhook_fresh(self):
        from routes.payment_vault import _reject_stale_webhook_timestamp

        fresh = datetime.now(timezone.utc).isoformat()
        assert _reject_stale_webhook_timestamp({"timestamp": fresh}) is None

    def test_reject_stale_webhook_numeric_timestamp(self):
        from routes.payment_vault import _reject_stale_webhook_timestamp

        ts = datetime.now(timezone.utc).timestamp()
        assert _reject_stale_webhook_timestamp({"timestamp": ts}) is None

    def test_reject_stale_webhook_bad_timestamp(self):
        from routes.payment_vault import _reject_stale_webhook_timestamp

        assert _reject_stale_webhook_timestamp({"timestamp": "not-a-date"}) is None


class TestUnlockVaultRoutes:
    def test_unlock_get(self, vault_owner_client):
        resp = vault_owner_client.get("/payment-vault/unlock")
        assert resp.status_code == 200

    def test_unlock_post_empty_password(self, vault_owner_client, mocker):
        mocker.patch(
            "routes.payment_vault._get_vault_for_current_tenant",
            return_value=MagicMock(),
        )
        resp = vault_owner_client.post("/payment-vault/unlock", data={"vault_password": ""})
        assert resp.status_code == 200

    def test_unlock_post_create_new_vault(self, vault_owner_client, mocker, mock_db):
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=None)
        mocker.patch("routes.payment_vault.PaymentVault")
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/unlock",
            data={"vault_password": "Secret123!"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_unlock_post_success(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/unlock",
            data={"vault_password": "good"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_unlock_post_wrong_password(self, vault_owner_client, mocker):
        vault = MagicMock()
        vault.is_locked_out.return_value = False
        vault.unlock_vault.return_value = False
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=vault)
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/unlock", data={"vault_password": "bad"})
        assert resp.status_code == 200

    def test_unlock_post_locked_out(self, vault_owner_client, mocker):
        vault = MagicMock()
        vault.is_locked_out.return_value = True
        vault.unlock_vault.return_value = False
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=vault)
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/unlock", data={"vault_password": "bad"})
        assert resp.status_code == 200


class TestVaultPageRoutes:
    def test_index(self, vault_owner_client):
        resp = vault_owner_client.get("/payment-vault/")
        assert resp.status_code == 200

    def test_dashboard_locked_redirect(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.get("/payment-vault/dashboard", follow_redirects=False)
        assert resp.status_code == 302

    def test_dashboard_unlocked(self, vault_owner_client, mock_unlocked_vault, mocker, mock_analytics):
        don = MagicMock(amount_usd=100, status="completed")
        q = MagicMock()
        q.filter_by.return_value.all.return_value = [don]
        q.filter.return_value.count.return_value = 1
        q.order_by.return_value.limit.return_value.all.return_value = [don]
        mocker.patch("routes.payment_vault.Donation.query", q)
        mocker.patch(
            "services.notification_service.SecurityService.get_security_status",
            return_value={"security_level": "ok"},
        )
        resp = vault_owner_client.get("/payment-vault/dashboard")
        assert resp.status_code == 200

    def test_settings_get_locked(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.get("/payment-vault/settings", follow_redirects=False)
        assert resp.status_code == 302

    def test_settings_post_update(self, vault_owner_client, mock_unlocked_vault, mock_db, mocker):
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/settings",
            data={
                "nowpayments_api_key": "key",
                "nowpayments_ipn_secret": "sec",
                "bitcoin_address": "btc",
                "paypal_mode": "sandbox",
                "min_donation_amount": "5",
                "max_donation_amount": "1000",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)

    def test_donations_list(self, vault_owner_client, mock_unlocked_vault, mocker):
        item = MagicMock()
        pag = MagicMock(items=[item], total=1, page=1, per_page=20, pages=1)
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        q.filter.return_value.count.return_value = 0
        q.with_entities.return_value.scalar.return_value = 0
        mocker.patch("routes.payment_vault.Donation.query", q)
        resp = vault_owner_client.get("/payment-vault/donations?status=pending&search=ali")
        assert resp.status_code == 200

    def test_packages_management(self, vault_owner_client, mock_unlocked_vault, mocker):
        pkg = MagicMock(slug="basic")
        mocker.patch("routes.payment_vault.Package.query").order_by.return_value.all.return_value = [pkg]
        pp_q = MagicMock()
        pp_q.join.return_value.filter.return_value.count.return_value = 2
        mocker.patch("routes.payment_vault.PackagePurchase.query", pp_q)
        resp = vault_owner_client.get("/payment-vault/packages-management")
        assert resp.status_code == 200

    def test_create_package_missing_names(self, vault_owner_client, mock_unlocked_vault):
        resp = vault_owner_client.post(
            "/payment-vault/package/create",
            data={"name_ar": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_create_package_duplicate_slug(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.Package.query").filter_by.return_value.first.return_value = MagicMock()
        resp = vault_owner_client.post(
            "/payment-vault/package/create",
            data={
                "name_ar": "باقة",
                "name_en": "Pack",
                "slug": "basic",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_create_package_success(self, vault_owner_client, mock_unlocked_vault, mocker, mock_db):
        mocker.patch("routes.payment_vault.Package.query").filter_by.return_value.first.return_value = None
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/package/create",
            data={
                "name_ar": "باقة",
                "name_en": "Pack",
                "price": "99",
                "features": "a\nb",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_edit_package_get(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.Package.query").get_or_404.return_value = MagicMock()
        resp = vault_owner_client.get("/payment-vault/package/1/edit")
        assert resp.status_code == 200

    def test_edit_package_post(self, vault_owner_client, mock_unlocked_vault, mocker, mock_db):
        pkg = MagicMock(price=10, max_users=1, max_branches=1)
        mocker.patch("routes.payment_vault.Package.query").get_or_404.return_value = pkg
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post(
            "/payment-vault/package/1/edit",
            data={
                "name_ar": "تعديل",
                "name_en": "Edit",
                "price": "50",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)

    def test_delete_package(self, vault_owner_client, mock_unlocked_vault, mocker, mock_db):
        pkg = MagicMock()
        mocker.patch("routes.payment_vault.Package.query").get_or_404.return_value = pkg
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        resp = vault_owner_client.post("/payment-vault/package/1/delete", follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_reports_page(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch(
            "services.analytics_service.AnalyticsService.get_revenue_by_period",
            return_value={"labels": [], "purchases": [], "donations": []},
        )
        mocker.patch(
            "services.analytics_service.AnalyticsService.get_payment_method_stats",
            return_value={},
        )
        mocker.patch(
            "services.analytics_service.AnalyticsService.get_package_performance",
            return_value={},
        )
        resp = vault_owner_client.get("/payment-vault/reports")
        assert resp.status_code == 200

    def test_lock_vault_post(self, vault_owner_client, mock_unlocked_vault, mocker, mock_db):
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/lock", follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_cards_page(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.CardPayment.query").order_by.return_value.all.return_value = []
        resp = vault_owner_client.get("/payment-vault/cards")
        assert resp.status_code == 200

    def test_card_decrypt(self, vault_owner_client, mock_unlocked_vault, mock_db, mocker):
        card = MagicMock()
        card.get_card_display.return_value = "****1111"
        card.to_dict.return_value = {"last_four": "1111"}
        mock_db.get.return_value = card
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post("/payment-vault/card/1/decrypt")
        assert resp.status_code == 200

    def test_change_password_get(self, vault_owner_client, mock_unlocked_vault):
        resp = vault_owner_client.get("/payment-vault/change-password")
        assert resp.status_code == 200

    def test_purchases_list(self, vault_owner_client, mock_unlocked_vault, mocker):
        pag = MagicMock(items=[], total=0, page=1, per_page=20, pages=0)
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        mocker.patch("routes.payment_vault.PackagePurchase.query", q)
        resp = vault_owner_client.get("/payment-vault/purchases")
        assert resp.status_code == 200

    def test_purchase_detail(self, vault_owner_client, mock_unlocked_vault, mocker):
        pur = MagicMock(to_dict=lambda: {"id": 1})
        mocker.patch("routes.payment_vault.PackagePurchase.query").get_or_404.return_value = pur
        resp = vault_owner_client.get("/payment-vault/purchase/1")
        assert resp.status_code == 200

    def test_donation_detail(self, vault_owner_client, mock_unlocked_vault, mocker):
        don = MagicMock()
        mocker.patch("routes.payment_vault.Donation.query").filter_by.return_value.first_or_404.return_value = don
        resp = vault_owner_client.get("/payment-vault/donation/1")
        assert resp.status_code == 200

    def test_auto_approve(self, vault_owner_client, mock_unlocked_vault, mocker, mock_db):
        mocker.patch("routes.payment_vault.Donation.query").filter_by.return_value.all.return_value = []
        resp = vault_owner_client.post("/payment-vault/auto-approve", follow_redirects=False)
        assert resp.status_code == 302

    def test_health_check(self, vault_owner_client, mocker):
        mocker.patch(
            "services.health_service.HealthCheckService.run_full_health_check",
            return_value={"overall_status": "healthy"},
        )
        resp = vault_owner_client.get("/payment-vault/health")
        assert resp.status_code == 200

    def test_health_check_unhealthy(self, vault_owner_client, mocker):
        mocker.patch(
            "services.health_service.HealthCheckService.run_full_health_check",
            return_value={"overall_status": "degraded"},
        )
        resp = vault_owner_client.get("/payment-vault/health")
        assert resp.status_code == 503

    def test_metrics(self, vault_owner_client, mocker):
        mocker.patch(
            "services.health_service.HealthCheckService.get_system_metrics",
            return_value={"cpu": 10},
        )
        resp = vault_owner_client.get("/payment-vault/metrics")
        assert resp.status_code == 200

    def test_v2_stats(self, vault_owner_client, mocker):
        mocker.patch(
            "services.analytics_service.AnalyticsService.get_daily_stats",
            return_value={"today_revenue": 0},
        )
        mocker.patch("routes.payment_vault.Donation.query").filter_by.return_value.count.return_value = 0
        resp = vault_owner_client.get("/payment-vault/api/v2/stats")
        assert resp.status_code == 200


class TestStripeWebhook:
    PAYLOAD = b'{"id":"evt_1","type":"payment_intent.succeeded","created_at":"2026-06-27T12:00:00+00:00"}'

    @pytest.fixture(autouse=True)
    def _common(self, mocker, mock_unlocked_vault):
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        mocker.patch("routes.payment_vault._reject_stale_webhook_timestamp", return_value=None)
        mocker.patch("routes.payment_vault.PaymentLog.log_action")

    def test_stripe_missing_secret(self, vault_owner_client, mocker):
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant").return_value.stripe_webhook_secret = ""
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"Stripe-Signature": "sig"},
        )
        assert resp.status_code == 503

    def test_stripe_missing_signature(self, vault_owner_client):
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=self.PAYLOAD,
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_stripe_invalid_signature(self, vault_owner_client, mocker):
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=False,
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"Stripe-Signature": "bad"},
        )
        assert resp.status_code == 403

    def test_stripe_success(self, vault_owner_client, mocker):
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_stripe_webhook",
            return_value={"success": True},
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            data=self.PAYLOAD,
            content_type="application/json",
            headers={"Stripe-Signature": "good"},
        )
        assert resp.status_code == 200


class TestVaultExports:
    def test_export_purchases(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.PackagePurchase.query").order_by.return_value.all.return_value = []
        mocker.patch(
            "services.export_service.ExportService.export_purchases_to_csv",
            return_value=MagicMock(),
        )
        mocker.patch("flask.send_file", return_value=MagicMock(status_code=200))
        resp = vault_owner_client.get("/payment-vault/export/purchases")
        assert resp.status_code == 200

    def test_export_donations(self, vault_owner_client, mock_unlocked_vault, mocker):
        q = MagicMock()
        q.filter_by.return_value.order_by.return_value.all.return_value = []
        mocker.patch("routes.payment_vault.Donation.query", q)
        mocker.patch(
            "services.export_service.ExportService.export_donations_to_csv",
            return_value=MagicMock(),
        )
        mocker.patch("flask.send_file", return_value=MagicMock(status_code=200))
        resp = vault_owner_client.get("/payment-vault/export/donations")
        assert resp.status_code == 200

    def test_export_cards(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.CardPayment.query").order_by.return_value.all.return_value = []
        mocker.patch(
            "services.export_service.ExportService.export_cards_to_csv",
            return_value=MagicMock(),
        )
        mocker.patch("flask.send_file", return_value=MagicMock(status_code=200))
        resp = vault_owner_client.get("/payment-vault/export/cards")
        assert resp.status_code == 200

    def test_export_report_pdf(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch("routes.payment_vault.PackagePurchase.query").all.return_value = []
        q = MagicMock()
        q.filter_by.return_value.all.return_value = []
        mocker.patch("routes.payment_vault.Donation.query", q)
        mocker.patch(
            "services.export_service.ExportService.generate_pdf_report",
            return_value="<html></html>",
        )
        resp = vault_owner_client.get("/payment-vault/export/report-pdf")
        assert resp.status_code == 200
