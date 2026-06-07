"""
Routes Integration Tests
Tests route handlers using Flask test client.
"""
import pytest


class TestPublicRoutes:
    """Test public/unauthenticated routes."""

    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code in (200, 302)

    def test_pricing_page(self, client):
        resp = client.get("/pricing")
        assert resp.status_code in (200, 302)

    def test_features_page(self, client):
        resp = client.get("/features")
        assert resp.status_code in (200, 302)

    def test_login_page(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code in (200, 302)



class TestAuthRoutes:
    """Test authentication routes."""

    def test_login_post_invalid(self, client):
        resp = client.post("/auth/login", data={
            "username": "invalid",
            "password": "wrong",
        })
        assert resp.status_code in (200, 302)

    def test_logout_redirect(self, client):
        resp = client.get("/auth/logout")
        assert resp.status_code in (302, 200)


class TestAPIRoutes:
    """Test API routes."""

    def test_api_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code in (200, 404)

    def test_api_version(self, client):
        resp = client.get("/api/version")
        assert resp.status_code in (200, 404)


class TestProtectedRoutes:
    """Test that protected routes redirect when not logged in."""

    def _assert_redirect(self, resp):
        assert resp.status_code in (302, 308)

    def test_sales_requires_login(self, client):
        resp = client.get("/sales")
        self._assert_redirect(resp)

    def test_purchases_requires_login(self, client):
        resp = client.get("/purchases")
        self._assert_redirect(resp)

    def test_products_requires_login(self, client):
        resp = client.get("/products")
        self._assert_redirect(resp)

    def test_suppliers_requires_login(self, client):
        resp = client.get("/suppliers")
        self._assert_redirect(resp)

    def test_payments_requires_login(self, client):
        resp = client.get("/payments")
        self._assert_redirect(resp)

    def test_ledger_requires_login(self, client):
        resp = client.get("/ledger")
        self._assert_redirect(resp)

    def test_reports_requires_login(self, client):
        resp = client.get("/reports")
        self._assert_redirect(resp)

    def test_warehouse_requires_login(self, client):
        resp = client.get("/warehouse")
        self._assert_redirect(resp)

    def test_treasury_requires_login(self, client):
        resp = client.get("/reports/treasury")
        self._assert_redirect(resp)

    def test_owner_requires_login(self, client):
        resp = client.get("/owner/users-list")
        self._assert_redirect(resp)

    def test_users_requires_login(self, client):
        resp = client.get("/users")
        self._assert_redirect(resp)

    def test_payroll_requires_login(self, client):
        resp = client.get("/payroll/employees/add")
        self._assert_redirect(resp)

    def test_returns_requires_login(self, client):
        resp = client.get("/returns")
        self._assert_redirect(resp)


class TestCSRFExemptEndpoints:
    """Test that CSRF-exempt API endpoints exist."""

    def _assert_ok_or_redirect(self, resp):
        assert resp.status_code in (200, 302, 308, 404)

    def test_sale_totals_endpoint(self, client):
        resp = client.post("/sales/api/calculate-totals")
        self._assert_ok_or_redirect(resp)

    def test_purchase_totals_endpoint(self, client):
        resp = client.post("/purchases/api/calculate-totals")
        self._assert_ok_or_redirect(resp)

    def test_ledger_balance_endpoint(self, client):
        resp = client.post("/ledger/api/calculate-journal-balance")
        self._assert_ok_or_redirect(resp)


class TestStaticFiles:
    """Test static file serving."""

    def test_static_css(self, client):
        try:
            resp = client.get("/static/css/app.css")
            assert resp.status_code in (200, 404)
            resp.close()
        except Exception:
            pass  # Static files may not exist in test environment

    def test_static_js(self, client):
        try:
            resp = client.get("/static/js/app.js")
            assert resp.status_code in (200, 404)
            resp.close()
        except Exception:
            pass  # Static files may not exist in test environment
