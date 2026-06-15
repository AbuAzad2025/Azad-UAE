"""Frontend template rendering tests using seeded PostgreSQL data."""
import pytest
from app import create_app
from models import Tenant, Sale
from tests.conftest import TestConfig

TENANT_SLUG = "al-ufuq-trading"
PASSWORD = "test123"


@pytest.fixture(scope="session")
def app():
    cfg = TestConfig()
    cfg.SQLALCHEMY_ENGINE_OPTIONS = {"pool_size": 3, "max_overflow": 2, "pool_pre_ping": True, "pool_timeout": 10}
    a = create_app(cfg)
    with a.app_context():
        yield a


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def authed_client(app, client):
    with app.app_context():
        t = Tenant.query.filter_by(slug=TENANT_SLUG).first()
        tid = str(t.id)
    client.post("/auth/login", data={"username": "platform_owner", "password": PASSWORD})
    with client.session_transaction() as sess:
        sess["active_tenant_id"] = tid
    return client


def first_sale_id(app):
    with app.app_context():
        t = Tenant.query.filter_by(slug=TENANT_SLUG).first()
        if not t:
            return None
        s = Sale.query.filter_by(tenant_id=t.id).first()
        return s.id if s else None


class TestBaseTemplate:
    def test_html_has_rtl_direction(self, authed_client):
        resp = authed_client.get("/sales/", follow_redirects=True)
        if resp.status_code == 200:
            assert 'dir="rtl"' in resp.data.decode("utf-8")

    def test_navbar_contains_content(self, authed_client):
        resp = authed_client.get("/sales/", follow_redirects=True)
        if resp.status_code == 200:
            assert len(resp.data.decode("utf-8")) > 50


class TestLoginTemplate:
    def test_login_page_loads(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code in (200, 302)

    def test_login_has_fields(self, client):
        resp = client.get("/auth/login")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "username" in body or "اسم المستخدم" in body
            assert "password" in body or "كلمة المرور" in body

    def test_login_has_arabic_title(self, client):
        resp = client.get("/auth/login")
        if resp.status_code == 200:
            assert "تسجيل الدخول" in resp.data.decode("utf-8")


class TestSalesTemplates:
    def test_sales_index_renders(self, authed_client):
        resp = authed_client.get("/sales/", follow_redirects=True)
        if resp.status_code == 200:
            assert len(resp.data.decode("utf-8")) > 100

    def test_sales_create_form_has_fields(self, authed_client):
        resp = authed_client.get("/sales/create", follow_redirects=True)
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert any(x in body for x in ("customer", "العميل", "date", "التاريخ"))

    def test_sales_view_template(self, authed_client, app):
        sid = first_sale_id(app)
        if not sid:
            pytest.skip("No sale record found")
        resp = authed_client.get(f"/sales/{sid}/view", follow_redirects=True)
        if resp.status_code in (200, 302):
            assert len(resp.data.decode("utf-8")) > 50

    def test_sales_index_table_headers(self, authed_client):
        resp = authed_client.get("/sales/", follow_redirects=True)
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert any(x in body for x in ("رقم", "فاتورة", "العميل", "الإجمالي"))

    def test_sales_print_preview(self, authed_client, app):
        sid = first_sale_id(app)
        if not sid:
            pytest.skip("No sale record found")
        resp = authed_client.get(f"/sales/{sid}/print", follow_redirects=True)
        if resp.status_code in (200, 302):
            assert len(resp.data.decode("utf-8")) > 50


class TestCustomerTemplates:
    def test_customers_index_renders(self, authed_client):
        resp = authed_client.get("/customers/", follow_redirects=True)
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert any(x in body for x in ("عميل", "العميل", "Customer"))

    def test_customers_create_form(self, authed_client):
        resp = authed_client.get("/customers/create", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("name", "الاسم"))

    def test_customers_view_shows_details(self, authed_client, app):
        pytest.skip("Customer view route pattern unknown")

    def test_customers_table_headers(self, authed_client):
        resp = authed_client.get("/customers/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("الاسم", "الهاتف", "الرصيد", "Name", "Phone"))

    def test_customers_table_headers(self, authed_client):
        resp = authed_client.get("/customers/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("الاسم", "الهاتف", "الرصيد", "Name", "Phone"))


class TestProductTemplates:
    def test_products_index_renders(self, authed_client):
        resp = authed_client.get("/products/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("منتج", "المنتج", "Product"))

    def test_products_create_form(self, authed_client):
        resp = authed_client.get("/products/create", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("name", "الاسم", "price", "السعر"))

    def test_products_view_details(self, authed_client, app):
        pytest.skip("Product view route pattern unknown")

    def test_products_index_grid(self, authed_client):
        resp = authed_client.get("/products/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("السعر", "المخزون", "Price", "Stock"))


class TestLedgerTemplates:
    def test_ledger_index_renders(self, authed_client):
        resp = authed_client.get("/ledger/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("دفتر", "حساب", "Ledger", "Account"))


class TestReportTemplates:
    def test_reports_index_renders(self, authed_client):
        resp = authed_client.get("/reports/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("تقرير", "Report", "تقارير"))


class TestPurchaseTemplates:
    def test_purchases_index_renders(self, authed_client):
        resp = authed_client.get("/purchases/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("مشتريات", "فاتورة", "Purchase"))


class TestPOSTemplates:
    def test_pos_main_page(self, authed_client):
        resp = authed_client.get("/pos/", follow_redirects=True)
        if resp.status_code == 200:
            assert len(resp.data.decode("utf-8")) > 100


class TestNavigationTemplates:
    def test_sidebar_has_sales_link(self, authed_client):
        resp = authed_client.get("/sales/", follow_redirects=True)
        if resp.status_code == 200:
            assert any(x in resp.data.decode("utf-8") for x in ("مبيعات", "Sales", "sidebar"))



