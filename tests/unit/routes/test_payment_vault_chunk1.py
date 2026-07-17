"""tests/unit/test_payment_vault_chunk1.py — Payment-vault API-heavy write endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# =============================================================================
#  Fixtures: service & model mocks
# =============================================================================


@pytest.fixture(autouse=True)
def _patch_db(mock_db):
    pass


@pytest.fixture
def mock_nowpayments(mocker):
    svc = mocker.MagicMock(name="NOWPaymentsService")
    svc.create_payment.return_value = {
        "success": True,
        "payment_id": "np_123",
        "pay_address": "1ABCxyz",
        "pay_amount": 100.0,
        "invoice_url": "https://nowpayments.io/invoice/xyz",
    }
    mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)
    return svc


@pytest.fixture
def mock_card_payment(mocker):
    """Patch CardPayment so instantiation + encrypt_card_data are controllable."""
    cp = mocker.MagicMock(name="CardPayment")
    cp.transaction_id = "CARD_1700000000"
    cp.get_card_display.return_value = "****1111"
    cp.encrypt_card_data.return_value = True
    mocker.patch("routes.payment_vault.CardPayment", return_value=cp)
    return cp


@pytest.fixture
def mock_package(mocker):
    pkg = mocker.MagicMock(name="Package")
    pkg.is_active = True
    pkg.name_ar = "الباقة الأساسية"
    pkg.id = 1
    mocker.patch("routes.payment_vault.Package")
    from routes.payment_vault import Package as PkgMod

    PkgMod.query.get_or_404.return_value = pkg
    PkgMod.query.get.return_value = pkg
    return pkg


@pytest.fixture
def mock_purchase(mocker):
    pur = mocker.MagicMock(name="PackagePurchase")
    pur.id = 1
    pur.amount_paid = 99.0
    pur.payment_status = "pending"
    pur.activation_status = "pending"
    pur.customer_email = "a@b.com"
    pur.transaction_id = "tx_1"
    pur.to_dict.return_value = {"id": 1, "amount": 99.0}
    mocker.patch("routes.payment_vault.PackagePurchase")
    from routes.payment_vault import PackagePurchase as pp

    pp.query.get_or_404.return_value = pur
    pp.query.filter_by.return_value.all.return_value = [pur]
    pp.query.paginate.return_value = _make_pagination([pur], 1, 20, 1)
    return pur


@pytest.fixture
def mock_donation(mocker):
    don = mocker.MagicMock(name="Donation")
    don.id = 1
    don.amount_usd = 50.0
    don.status = "pending"
    don.donor_name = "Ali"
    don.donor_email = "ali@test.com"
    don.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    don.transaction_type = "donation"
    mocker.patch("routes.payment_vault.Donation")
    from routes.payment_vault import Donation as DMod

    DMod.query.filter_by.return_value.first_or_404.return_value = don
    DMod.query.filter_by.return_value.first.return_value = don
    DMod.query.filter_by.return_value.count.return_value = 3
    DMod.query.with_entities.return_value.scalar.return_value = 150.0
    DMod.query.order_by.return_value.paginate.return_value = _make_pagination(
        [don], 1, 20, 1
    )
    return don


@pytest.fixture
def mock_analytics(mocker):
    daily = {"today_revenue": 500.0, "today_transactions": 10}
    revenue = {
        "labels": ["Jan", "Feb"],
        "purchases": [100, 200],
        "donations": [50, 75],
    }
    payment_methods = {"crypto": 3, "card": 5}
    customer_behavior = {"new": 2, "returning": 8}
    package_perf = {"basic": 10, "pro": 5}

    mocker.patch(
        "services.analytics_service.AnalyticsService.get_daily_stats",
        return_value=daily,
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_revenue_by_period",
        return_value=revenue,
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_payment_method_stats",
        return_value=payment_methods,
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_customer_behavior",
        return_value=customer_behavior,
    )
    mocker.patch(
        "services.analytics_service.AnalyticsService.get_package_performance",
        return_value=package_perf,
    )
    return daily


@pytest.fixture
def mock_notifications(mocker):
    notes = [
        {"id": 1, "text": "New donation"},
        {"id": 2, "text": "Payment received"},
    ]
    mocker.patch(
        "services.notification_service.NotificationService.get_recent_notifications",
        return_value=notes,
    )
    return notes


@pytest.fixture
def mock_security(mocker):
    mocker.patch(
        "services.notification_service.SecurityService.get_security_status",
        return_value={"security_level": "high"},
    )


@pytest.fixture
def mock_gl_service(mocker):
    return mocker.patch(
        "services.donation_gl_service.DonationGLService.post_completed_donation"
    )


@pytest.fixture
def mock_payment_log(mocker):
    return mocker.patch("routes.payment_vault.PaymentLog.log_action")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_pagination(items, page, per_page, total):
    pages = (total + per_page - 1) // per_page if total else 0
    p = MagicMock(name="Pagination")
    p.items = items
    p.page = page
    p.per_page = per_page
    p.total = total
    p.pages = pages
    p.has_next = page < pages
    p.has_prev = page > 1
    p.prev_num = page - 1 if p.has_prev else None
    p.next_num = page + 1 if p.has_next else None
    return p


# =============================================================================
#  /process-payment
# =============================================================================


class TestProcessPayment:
    ENDPOINT = "/payment-vault/process-payment"

    def test_crypto_happy(self, vault_owner_client, mock_nowpayments):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={"payment_method": "crypto", "amount": 100, "crypto_currency": "btc"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["payment_id"] == "np_123"
        mock_nowpayments.create_payment.assert_called_once()
        assert mock_nowpayments.create_payment.call_args.kwargs["amount"] == 100.0

    def test_crypto_passes_all_fields(self, vault_owner_client, mock_nowpayments):
        payload = {
            "payment_method": "crypto",
            "amount": 50,
            "crypto_currency": "eth",
            "customer_email": "buyer@test.com",
            "description": "Donation",
            "type": "donation",
            "package": "basic",
            "customer_name": "Ahmed",
            "customer_phone": "0500000000",
            "donor_name": "Ahmed",
            "donor_email": "ahmed@test.com",
            "donor_message": "بارك الله فيكم",
        }
        resp = vault_owner_client.post(self.ENDPOINT, json=payload)
        assert resp.status_code == 200
        kw = mock_nowpayments.create_payment.call_args.kwargs
        assert kw["amount"] == 50.0
        assert kw["crypto_currency"] == "eth"
        assert kw["customer_email"] == "buyer@test.com"

    def test_crypto_invalid_amount_returns_422(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={"payment_method": "crypto", "amount": "not-a-number"},
        )
        assert resp.status_code == 422

    def test_card_happy(self, vault_owner_client, mock_card_payment, mock_payment_log):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={
                "payment_method": "card",
                "amount": 50,
                "card_number": "4111111111111111",
                "cvv": "123",
                "expiry": "12/28",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["transaction_id"] == "CARD_1700000000"
        mock_card_payment.encrypt_card_data.assert_called_once_with(
            "4111111111111111", "123", "12/28"
        )
        mock_payment_log.assert_called_once()

    def test_card_amount_below_minimum_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={
                "payment_method": "card",
                "amount": 0.5,
                "card_number": "4111111111111111",
                "cvv": "123",
                "expiry": "12/28",
            },
        )
        assert resp.status_code == 400
        assert "الحد الأدنى" in resp.get_json()["error"]

    def test_card_invalid_amount_returns_422(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={
                "payment_method": "card",
                "amount": "bad",
                "card_number": "4111111111111111",
            },
        )
        assert resp.status_code == 422

    def test_card_short_number_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={
                "payment_method": "card",
                "amount": 50,
                "card_number": "123",
                "cvv": "123",
                "expiry": "12/28",
            },
        )
        assert resp.status_code == 400

    def test_card_encrypt_failure_returns_500(
        self, vault_owner_client, mock_card_payment
    ):
        mock_card_payment.encrypt_card_data.return_value = False
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={
                "payment_method": "card",
                "amount": 50,
                "card_number": "4111111111111111",
                "cvv": "123",
                "expiry": "12/28",
            },
        )
        assert resp.status_code == 500

    def test_missing_body_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT, data=b"not-json", content_type="application/json"
        )
        assert resp.status_code == 400

    def test_empty_json_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(self.ENDPOINT, json={})
        assert resp.status_code == 400

    def test_unsupported_method_returns_400(self, vault_owner_client):
        resp = vault_owner_client.post(
            self.ENDPOINT,
            json={"payment_method": "paypal", "amount": 50},
        )
        assert resp.status_code == 400


# =============================================================================
#  /package/<id>/toggle
# =============================================================================


class TestTogglePackage:
    def test_toggle_active_to_inactive(self, vault_owner_client, mock_package, mock_db):
        mock_package.is_active = True
        resp = vault_owner_client.post("/payment-vault/package/1/toggle")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert mock_package.is_active is False

    def test_toggle_inactive_to_active(self, vault_owner_client, mock_package, mock_db):
        mock_package.is_active = False
        resp = vault_owner_client.post("/payment-vault/package/1/toggle")
        assert resp.status_code == 200
        assert mock_package.is_active is True

    def test_toggle_rollback_returns_500(
        self, vault_owner_client, mock_package, mock_db
    ):
        mock_db.commit.side_effect = Exception("DB fail")
        resp = vault_owner_client.post("/payment-vault/package/1/toggle")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["success"] is False


# =============================================================================
#  /payment-vault/api/package-stats/<id>
# =============================================================================


class TestPackageStats:
    @pytest.fixture(autouse=True)
    def _mock_package_purchase(self, mocker):
        mock_q = mocker.patch("routes.payment_vault.PackagePurchase.query")
        mock_q.filter_by.return_value = mock_q
        mock_q.all.return_value = []
        return mock_q

    def test_returns_aggregated_stats(
        self, vault_owner_client, _mock_package_purchase, mock_package
    ):
        _mock_package_purchase.all.return_value = [
            MagicMock(amount_paid=100, payment_status="completed"),
            MagicMock(amount_paid=50, payment_status="completed"),
            MagicMock(amount_paid=30, payment_status="pending"),
            MagicMock(amount_paid=20, payment_status="failed"),
        ]

        resp = vault_owner_client.get("/payment-vault/api/package-stats/1")
        assert resp.status_code == 200
        stats = resp.get_json()
        assert stats["total_sales"] == 4
        assert stats["total_revenue"] == 150
        assert stats["completed"] == 2
        assert stats["pending"] == 1
        assert stats["failed"] == 1

    def test_zero_sales(self, vault_owner_client, _mock_package_purchase, mock_package):
        resp = vault_owner_client.get("/payment-vault/api/package-stats/1")
        assert resp.status_code == 200
        stats = resp.get_json()
        assert stats["total_sales"] == 0
        assert stats["total_revenue"] == 0


# =============================================================================
#  /api/notifications
# =============================================================================


class TestNotifications:
    def test_returns_notifications(self, vault_owner_client, mock_notifications):
        resp = vault_owner_client.get("/payment-vault/api/notifications")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert len(body["notifications"]) == 2
        assert body["count"] == 2

    def test_custom_limit(self, vault_owner_client, mocker):
        notes = [{"id": i, "text": f"n{i}"} for i in range(5)]
        mocker.patch(
            "services.notification_service.NotificationService.get_recent_notifications",
            return_value=notes,
        )
        resp = vault_owner_client.get("/payment-vault/api/notifications?limit=5")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["notifications"]) == 5


# =============================================================================
#  /api/live-stats
# =============================================================================


class TestLiveStats:
    def test_returns_live_stats(
        self, vault_owner_client, mock_analytics, mock_security, mocker
    ):
        mock_don_q = MagicMock()
        mock_don_q.filter_by.return_value.count.return_value = 5
        mocker.patch("routes.payment_vault.Donation.query", mock_don_q)
        resp = vault_owner_client.get("/payment-vault/api/live-stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["daily_revenue"] == 500.0
        assert body["daily_transactions"] == 10
        assert body["security_level"] == "high"


# =============================================================================
#  /api/v2/purchases
# =============================================================================


class TestV2Purchases:
    @pytest.fixture(autouse=True)
    def _mock_pp(self, mocker):
        q = MagicMock(name="pp_query")
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        mock_pag = MagicMock(name="pp_pag")
        mock_pag.items = [
            MagicMock(to_dict=MagicMock(return_value={"id": 1, "amount": 99.0}))
        ]
        mock_pag.page = 1
        mock_pag.per_page = 20
        mock_pag.total = 1
        mock_pag.pages = 1
        mock_pag.has_next = False
        mock_pag.has_prev = False
        mock_pag.prev_num = None
        mock_pag.next_num = None
        q.paginate.return_value = mock_pag
        mocker.patch("routes.payment_vault.PackagePurchase.query", q)
        return q

    def test_basic_pagination(self, vault_owner_client, _mock_pp):
        resp = vault_owner_client.get("/payment-vault/api/v2/purchases")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["version"] == "2.0"
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["pagination"]["total"] == 1

    def test_filter_by_status(self, vault_owner_client, _mock_pp):
        _mock_pp.paginate.return_value.items = []
        _mock_pp.paginate.return_value.total = 0
        resp = vault_owner_client.get(
            "/payment-vault/api/v2/purchases?status=completed"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) == 0

    def test_search_filter(self, vault_owner_client, _mock_pp):
        resp = vault_owner_client.get("/payment-vault/api/v2/purchases?search=ali")
        assert resp.status_code == 200

    def test_sort_and_order(self, vault_owner_client, _mock_pp):
        resp = vault_owner_client.get(
            "/payment-vault/api/v2/purchases?sort_by=amount_paid&order=asc"
        )
        assert resp.status_code == 200


# =============================================================================
#  /api/v2/donations
# =============================================================================


class TestV2Donations:
    @pytest.fixture(autouse=True)
    def _mock_don_query(self, mocker):
        q = MagicMock(name="don_query")
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        mock_pag = MagicMock(name="don_pag")
        mock_pag.items = [
            MagicMock(
                id=1,
                donor_name="Ali",
                donor_email="a@b.com",
                amount_usd=50.0,
                payment_method="card",
                status="pending",
                created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
                isoformat=lambda: "2024-06-01T00:00:00+00:00",
            )
        ]
        mock_pag.page = 1
        mock_pag.per_page = 20
        mock_pag.total = 1
        mock_pag.pages = 1
        q.order_by.return_value.paginate.return_value = mock_pag
        mocker.patch("routes.payment_vault.Donation.query", q)
        return q

    def test_basic_pagination(self, vault_owner_client, _mock_don_query):
        resp = vault_owner_client.get("/payment-vault/api/v2/donations")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["version"] == "2.0"
        assert body["success"] is True
        assert len(body["data"]) == 1

    def test_filter_by_status(self, vault_owner_client, _mock_don_query):
        _mock_don_query.order_by.return_value.paginate.return_value.items = []
        resp = vault_owner_client.get(
            "/payment-vault/api/v2/donations?status=completed"
        )
        assert resp.status_code == 200

    def test_search_filter(self, vault_owner_client, _mock_don_query):
        resp = vault_owner_client.get("/payment-vault/api/v2/donations?search=ali")
        assert resp.status_code == 200


# =============================================================================
#  /donation/<id>/approve / /donation/<id>/reject
# =============================================================================


class TestDonationApproveReject:
    def test_approve_success(
        self, vault_owner_client, mock_donation, mock_gl_service, mock_db
    ):
        resp = vault_owner_client.post(
            "/payment-vault/donation/1/approve", follow_redirects=False
        )
        assert resp.status_code == 302
        assert mock_donation.status == "completed"
        mock_gl_service.assert_called_once_with(mock_donation)

    def test_approve_rollback(
        self, vault_owner_client, mock_donation, mock_gl_service, mock_db
    ):
        mock_gl_service.side_effect = Exception("GL post failed")
        resp = vault_owner_client.post(
            "/payment-vault/donation/1/approve", follow_redirects=False
        )
        assert resp.status_code == 302
        mock_db.rollback.assert_not_called()

    def test_reject_success(self, vault_owner_client, mock_donation, mock_db):
        resp = vault_owner_client.post(
            "/payment-vault/donation/1/reject", follow_redirects=False
        )
        assert resp.status_code == 302
        assert mock_donation.status == "failed"

    def test_reject_rollback(self, vault_owner_client, mock_donation, mock_db):
        mock_db.commit.side_effect = Exception("DB fail")
        resp = vault_owner_client.post(
            "/payment-vault/donation/1/reject", follow_redirects=False
        )
        assert resp.status_code == 302
        mock_db.rollback.assert_called_once()


# =============================================================================
#  /purchase/<id>/activate
# =============================================================================


class TestActivatePurchase:
    def test_activate_success(
        self, vault_owner_client, mock_purchase, mock_donation, mock_db
    ):
        assert mock_purchase.activation_status == "pending"
        resp = vault_owner_client.post(
            "/payment-vault/purchase/1/activate", follow_redirects=False
        )
        assert resp.status_code == 302
        assert mock_purchase.activation_status == "activated"
        assert mock_purchase.payment_status == "completed"
        assert mock_donation.status == "completed"

    def test_activate_rollback(
        self, vault_owner_client, mock_purchase, mock_donation, mock_db
    ):
        mock_db.commit.side_effect = Exception("DB fail")
        resp = vault_owner_client.post(
            "/payment-vault/purchase/1/activate", follow_redirects=False
        )
        assert resp.status_code == 302
        mock_db.rollback.assert_called_once()
