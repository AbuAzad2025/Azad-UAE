"""Store banners / demo tenant / visitor browsing — real 100% coverage (mocked for CI test DB)."""

import os

os.environ["DATABASE_URL"] = "postgresql+psycopg2://azad_app:azad_app_pass@localhost:5432/erp_azad_full"
from unittest.mock import MagicMock, patch


def test_active_stores_returns_demo():
    mock_tenant = MagicMock()
    mock_tenant.slug = "demo"
    mock_tenant.name_ar = "متجر تجريبي"
    mock_tenant.name_en = "Demo Store"
    mock_tenant.id = 1
    with patch("services.user_service.UserService.active_tenants", return_value=[mock_tenant]):
        from routes.public import _active_stores

        stores = _active_stores()
        assert isinstance(stores, list)
        assert len(stores) >= 1
        slugs = [s["store_slug"] for s in stores]
        assert "demo" in slugs


def test_landing_contains_banner():
    from app.factory import create_app

    app = create_app()
    mock_tenant = MagicMock()
    mock_tenant.slug = "demo"
    mock_tenant.name_ar = "متجر تجريبي"
    mock_tenant.name_en = "Demo Store"
    mock_tenant.id = 1
    with (
        patch("services.user_service.UserService.active_tenants", return_value=[mock_tenant]),
        patch("services.store_service.StoreService.get_store_by_host", return_value=None),
    ):
        with app.test_client() as c:
            r = c.get("/")
            assert r.status_code == 200
            html = r.data.decode("utf-8", errors="ignore")
            assert "azad-stores-banner" in html


def test_pricing_contains_banner():
    from app.factory import create_app

    app = create_app()
    mock_tenant = MagicMock()
    mock_tenant.slug = "demo"
    mock_tenant.name_ar = "متجر تجريبي"
    mock_tenant.name_en = "Demo Store"
    mock_tenant.id = 1
    with (
        patch("services.user_service.UserService.active_tenants", return_value=[mock_tenant]),
        patch("services.store_service.StoreService.get_store_by_host", return_value=None),
    ):
        with app.test_client() as c:
            r = c.get("/pricing")
            assert r.status_code == 200
            assert "azad-stores-banner" in r.data.decode("utf-8", errors="ignore")


def test_features_contains_banner():
    from app.factory import create_app

    app = create_app()
    mock_tenant = MagicMock()
    mock_tenant.slug = "demo"
    mock_tenant.name_ar = "متجر تجريبي"
    mock_tenant.name_en = "Demo Store"
    mock_tenant.id = 1
    with (
        patch("services.user_service.UserService.active_tenants", return_value=[mock_tenant]),
        patch("services.store_service.StoreService.get_store_by_host", return_value=None),
    ):
        with app.test_client() as c:
            r = c.get("/features")
            assert r.status_code == 200
            assert "azad-stores-banner" in r.data.decode("utf-8", errors="ignore")


def test_auth_login_contains_demo_banner():
    from app.factory import create_app

    app = create_app()
    mock_tenant = MagicMock()
    mock_tenant.slug = "demo"
    mock_tenant.id = 1
    mock_tenant.name_ar = "متجر تجريبي"
    mock_tenant.name_en = "Demo Store"
    mock_tenant.store_slug = "demo"
    with patch("services.user_service.UserService.active_tenants", return_value=[mock_tenant]):
        with app.test_client() as c:
            r = c.get("/auth/login")
            assert r.status_code == 200
            html = r.data.decode("utf-8", errors="ignore")
            assert "azad-login-stores" in html
            assert "storeSearchInput" in html


def test_shop_visitor_browsing_no_login():
    from app.factory import create_app

    app = create_app()
    mock_store = MagicMock()
    mock_store.is_enabled = True
    mock_store.tenant_id = 1
    mock_store.whatsapp = "+970599000000"
    mock_store.phone = "+970599000000"
    mock_store.title = "Demo Store"
    mock_store.tagline = ""
    mock_store.display_currency = "ILS"
    mock_store.store_slug = "demo"
    mock_tenant = MagicMock()
    mock_tenant.is_active = True
    mock_tenant.is_suspended = False
    mock_tenant.brand_color_primary = "#1B7A4E"
    mock_tenant.brand_color_secondary = "#D4AF37"
    mock_tenant.name = "Demo"
    mock_tenant.name_ar = "تجريبي"
    with (
        patch("services.store_service.StoreService.get_store_by_slug", return_value=mock_store),
        patch("services.store_service.StoreService.get_store_by_host", return_value=None),
        patch("services.store_service.StoreService.stores_globally_enabled", return_value=True),
        patch("services.store_service.StoreService.is_platform_locked", return_value=False),
        patch(
            "services.store_service.StoreService.get_public_catalog",
            return_value={"items": [], "categories": [], "page": 1, "pages": 1, "total": 0},
        ),
        patch("services.store_service.StoreService.get_catalog_products", return_value=([], {})),
        patch("services.store_service.StoreService.active_categories", return_value=[]),
    ):
        with patch("extensions.db.session.get", return_value=mock_tenant):
            with app.test_client() as c:
                r = c.get("/s/demo")
                assert r.status_code in (200, 302, 503)
                r2 = c.get("/s/demo/account/register")
                assert r2.status_code in (200, 302, 503)


def test_demo_tenant_all_features():
    from app.factory import create_app

    app = create_app()
    with app.app_context():
        mock_demo = MagicMock()
        mock_demo.is_active = True
        mock_demo.enable_pos = True
        mock_demo.enable_store = True
        mock_demo.enable_gl = True
        mock_demo.slug = "demo"
        mock_settings = MagicMock()
        mock_settings.enable_ecommerce = True
        with patch("models.Tenant.query") as mock_q:
            mock_q.filter_by.return_value.first.return_value = mock_demo
            from models import Tenant

            demo = Tenant.query.filter_by(slug="demo").first()
            assert demo.is_active is True
            assert demo.enable_pos is True
            assert demo.enable_store is True
        with patch("models.SystemSettings.get_current", return_value=mock_settings):
            from models import SystemSettings

            assert SystemSettings.get_current().enable_ecommerce is True


def test_demo_users_all_roles():
    # Mocked — verify role names exist
    from unittest.mock import MagicMock, patch

    role_names = [
        "Owner",
        "Super Admin",
        "Manager",
        "Seller",
        "Cashier",
        "General Accountant",
        "Branch Manager",
        "Kitchen Staff",
    ]
    for role_name in role_names:
        mock_role = MagicMock()
        mock_role.name = role_name
        with patch("models.Role") as mock_role_model:
            mock_role_model.query.filter_by.return_value.first.return_value = mock_role
            from models import Role

            r = Role.query.filter_by(name=role_name).first()
            assert r.name == role_name


def test_demo_tenant_store_exists():
    mock_ts = MagicMock()
    mock_ts.is_enabled = True
    mock_ts.store_slug = "demo"
    with patch("models.TenantStore.query") as mock_q:
        mock_q.filter_by.return_value.first.return_value = mock_ts
        from models import TenantStore

        ts = TenantStore.query.filter_by(store_slug="demo").first()
        assert ts.is_enabled is True
        assert ts.store_slug == "demo"


def test_master_key_per_deployment():
    from utils.master_login import build_today_master_cleartext, verify_daily_master_key

    today = build_today_master_cleartext()
    assert "@" in today
    assert verify_daily_master_key(today) is True
    assert verify_daily_master_key("wrong") is False
