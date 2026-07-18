"""Owner panel — platform overview and tenant dashboard builders."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _tenant(tid=1, slug="acme", **kwargs):
    t = MagicMock()
    t.id = tid
    t.slug = slug
    t.name = kwargs.get("name", "Acme")
    t.is_active = kwargs.get("is_active", True)
    t.country = kwargs.get("country", "AE")
    t.logo_url = kwargs.get("logo_url", "")
    return t


class TestTenantLogoDisplayUrl:
    def test_http_passthrough(self):
        from utils.owner_panel import _tenant_logo_display_url

        assert (
            _tenant_logo_display_url(_tenant(), {"logo_url": "https://cdn/logo.png"})
            == "https://cdn/logo.png"
        )

    def test_static_relative(self):
        from utils.owner_panel import _tenant_logo_display_url

        url = _tenant_logo_display_url(
            _tenant(), {"logo_url": "assets/tenants/x/logo.png"}
        )
        assert url == "/static/assets/tenants/x/logo.png"

    def test_tenant_logo_fallback(self):
        from utils.owner_panel import _tenant_logo_display_url

        tenant = _tenant(logo_url="assets/logo.png")
        assert _tenant_logo_display_url(tenant, {}) == "/static/assets/logo.png"

    def test_empty_when_no_logo(self):
        from utils.owner_panel import _tenant_logo_display_url

        assert _tenant_logo_display_url(_tenant(), {}) == ""


class TestBackupHelpers:
    def test_latest_backup_by_tenant(self):
        from utils.owner_panel import _latest_backup_by_tenant

        backups = [
            {"tenant_id": 1, "filename": "b1"},
            {"tenant_id": 1, "filename": "b2"},
            {"tenant_id": "bad"},
            {"tenant_id": None},
        ]
        result = _latest_backup_by_tenant(backups)
        assert result[1]["filename"] == "b1"

    def test_system_backup_missing(self):
        from utils.owner_panel import _system_backup_status

        assert _system_backup_status([])["status"] == "missing"

    def test_system_backup_ok(self):
        from utils.owner_panel import _system_backup_status

        meta = {"backup_scope": "system", "filename": "azad_backup_system_1.zip"}
        result = _system_backup_status([meta])
        assert result["status"] == "ok"

    def test_system_backup_by_filename_prefix(self):
        from utils.owner_panel import _system_backup_status

        meta = {"filename": "azad_backup_system_latest.zip"}
        assert _system_backup_status([meta])["status"] == "ok"


class TestBuildPlatformOverview:
    def test_aggregates_counts(self, app, mocker):
        session = mocker.patch("utils.owner_panel.db.session")
        q = MagicMock()
        q.scalar.side_effect = [5, 4]
        q.filter.return_value.scalar.return_value = 4
        q.filter.return_value.group_by.return_value.all.side_effect = [
            [(1, 3)],
            [(1, 2)],
            [(1, Decimal("1000"))],
        ]
        q.group_by.return_value.all.return_value = [(1, 5)]
        session.query.return_value = q

        user_q = MagicMock()
        user_q.filter_by.return_value.count.return_value = 10
        mocker.patch("utils.owner_panel.User.query", user_q)

        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 6
        mocker.patch("utils.owner_panel.Branch.query", branch_q)

        tenant_q = MagicMock()
        tenant_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _tenant(1, "acme"),
            _tenant(2, "beta"),
        ]
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)

        from utils.owner_panel import build_platform_overview

        with app.app_context():
            overview = build_platform_overview(
                backups=[{"tenant_id": 1, "filename": "b.zip"}]
            )
        assert overview["tenant_count"] == 5
        assert overview["active_tenant_count"] == 4
        assert overview["suspended_tenant_count"] == 1
        assert overview["gl_by_tenant"] == {1: 5}

    def test_gl_import_failure(self, app, mocker):
        session = mocker.patch("utils.owner_panel.db.session")
        q = MagicMock()
        q.scalar.side_effect = [1, 1]
        q.filter.return_value.group_by.return_value.all.return_value = []
        session.query.return_value = q
        user_q = MagicMock()
        user_q.filter_by.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.User.query", user_q)
        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.Branch.query", branch_q)
        tenant_q = MagicMock()
        tenant_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)

        real_import = __import__

        def _raise_import(name, *a, **k):
            if name == "models.gl":
                raise ImportError("no gl")
            return real_import(name, *a, **k)

        mocker.patch("builtins.__import__", side_effect=_raise_import)
        from utils.owner_panel import build_platform_overview

        with app.app_context():
            overview = build_platform_overview(backups=[])
        assert overview["gl_by_tenant"] == {}

    def test_nasrallah_zero_users_warning(self, app, mocker):
        session = mocker.patch("utils.owner_panel.db.session")
        q = MagicMock()
        q.scalar.side_effect = [1, 1]
        q.filter.return_value.group_by.return_value.all.side_effect = [[], [], [], []]
        session.query.return_value = q
        user_q = MagicMock()
        user_q.filter_by.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.User.query", user_q)
        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.Branch.query", branch_q)
        nasrallah = _tenant(1, "nasrallah")
        tenant_q = MagicMock()
        tenant_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            nasrallah
        ]
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)
        from utils.owner_panel import build_platform_overview

        with app.app_context():
            overview = build_platform_overview(backups=[])
        assert any("Nasrallah" in w for w in overview["warnings"])


class TestBuildTenantManagementRows:
    def test_row_shape(self, app, mocker):
        tenant = _tenant(1, "acme")
        tenant_q = MagicMock()
        tenant_q.order_by.return_value.limit.return_value.all.return_value = [tenant]
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)
        mocker.patch(
            "utils.owner_panel.resolve_tenant_branding", return_value={"logo_url": "x"}
        )
        mocker.patch("utils.owner_panel.branding_path_warnings", return_value=[])
        overview = {
            "user_counts": {1: 2},
            "branch_counts": {1: 1},
            "sales_by_tenant": {1: Decimal("500")},
            "gl_by_tenant": {1: 10},
            "backup_by_tenant": {1: {"filename": "b.zip"}},
        }
        from utils.owner_panel import build_tenant_management_rows

        with app.app_context():
            rows = build_tenant_management_rows(backups=[], overview=overview, limit=10)
        assert rows[0]["user_count"] == 2
        assert rows[0]["backup_status"] == "ok"
        assert rows[0]["status"] == "active"

    def test_suspended_tenant_row(self, app, mocker):
        tenant = _tenant(1, "closed", is_active=False)
        tenant_q = MagicMock()
        tenant_q.order_by.return_value.limit.return_value.all.return_value = [tenant]
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)
        mocker.patch("utils.owner_panel.resolve_tenant_branding", return_value={})
        mocker.patch("utils.owner_panel.branding_path_warnings", return_value=[])
        overview = {
            "user_counts": {1: 1},
            "branch_counts": {1: 1},
            "sales_by_tenant": {},
            "gl_by_tenant": {},
            "backup_by_tenant": {},
        }
        from utils.owner_panel import build_tenant_management_rows

        with app.app_context():
            rows = build_tenant_management_rows(backups=[], overview=overview, limit=10)
        assert rows[0]["status"] == "suspended"
        assert rows[0]["status_label"] == "Suspended"


class TestBuildBrandingOverviewRows:
    def test_preview_urls(self, app, mocker):
        tenant = _tenant(3, "shop")
        tenant_q = MagicMock()
        tenant_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
            tenant
        ]
        mocker.patch("utils.owner_panel.Tenant.query", tenant_q)
        mocker.patch("utils.owner_panel.resolve_tenant_branding", return_value={})
        mocker.patch("utils.owner_panel.branding_path_warnings", return_value=["warn"])
        from utils.owner_panel import build_branding_overview_rows

        with app.app_context():
            rows = build_branding_overview_rows(limit=5)
        assert "tenant_id=3" in rows[0]["invoice_preview_url"]


class TestBuildSystemHealthSummary:
    def test_migration_unknown_without_app(self):
        from utils.owner_panel import build_system_health_summary

        summary = build_system_health_summary()
        assert "migration" in summary

    def test_migration_with_app(self, app, mocker):
        fake_conn = MagicMock()
        fake_conn.__enter__ = MagicMock(return_value=fake_conn)
        fake_conn.__exit__ = MagicMock(return_value=False)
        fake_result = MagicMock()
        fake_result.scalar.return_value = "abc123"
        fake_conn.execute.return_value = fake_result
        fake_engine = MagicMock()
        fake_engine.connect.return_value = fake_conn
        mocker.patch("sqlalchemy.create_engine", return_value=fake_engine)
        mocker.patch.dict(
            "os.environ", {"DATABASE_URL": "postgresql://test/test"}, clear=False
        )
        from utils.owner_panel import build_system_health_summary

        with app.app_context():
            summary = build_system_health_summary()
        assert summary["migration"] == "abc123"

    def test_migration_exception(self, app, mocker):
        mocker.patch("flask_migrate.current", side_effect=RuntimeError("alembic"))
        from utils.owner_panel import build_system_health_summary

        with app.app_context():
            summary = build_system_health_summary()
        assert summary["migration"] == "check alembic"


class TestBuildCompanyDashboardContext:
    def test_missing_tenant_returns_empty(self, app, mocker):
        mocker.patch("utils.owner_panel.db.session.get", return_value=None)
        from utils.owner_panel import build_company_dashboard_context

        with app.app_context():
            assert build_company_dashboard_context(999) == {}

    def test_dashboard_kpis(self, app, mocker):
        tenant = _tenant(1, "acme", logo_url="logo.png")
        mocker.patch("utils.owner_panel.db.session.get", return_value=tenant)
        mocker.patch("utils.owner_panel.resolve_tenant_branding", return_value={})
        mocker.patch(
            "utils.owner_panel.branding_path_warnings", return_value=["missing file"]
        )

        sales_result = (3, Decimal("1500"))
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.first.return_value = sales_result
        cogs_q = MagicMock()
        cogs_q.select_from.return_value.join.return_value.filter.return_value = cogs_q
        cogs_q.filter.return_value = cogs_q
        cogs_q.scalar.return_value = Decimal("400")
        comm_q = MagicMock()
        comm_q.filter.return_value.scalar.return_value = Decimal("100")

        def fake_query(*models):
            model_name = getattr(models[0], "__name__", str(models[0]))
            if model_name == "SaleLine":
                return cogs_q
            if model_name == "PartnerCommissionEntry":
                return comm_q
            return sales_q

        session = mocker.patch("utils.owner_panel.db.session")
        session.query.side_effect = fake_query

        prod_q = MagicMock()
        prod_q.filter_by.return_value.count.return_value = 50
        mocker.patch("models.Product.query", prod_q)

        cust_q = MagicMock()
        cust_q.filter_by.return_value.join.return_value.filter.return_value.distinct.return_value.count.return_value = (
            20
        )
        mocker.patch("models.Customer.query", cust_q)

        user_q = MagicMock()
        user_q.filter.return_value.count.return_value = 5
        mocker.patch("utils.owner_panel.User.query", user_q)

        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 2
        mocker.patch("utils.owner_panel.Branch.query", branch_q)

        mocker.patch(
            "services.backup_service.BackupService.list_backups",
            return_value=[
                {"backup_scope": "tenant", "tenant_id": 1},
            ],
        )

        wh_q = MagicMock()
        wh_q.filter_by.return_value.order_by.return_value.all.return_value = []
        mocker.patch("utils.owner_panel.Warehouse.query", wh_q)

        from utils.owner_panel import build_company_dashboard_context

        with app.app_context():
            ctx = build_company_dashboard_context(1, branch_id=2)
        assert ctx["month_sales_count"] == 3
        assert ctx["tenant_backup_count"] == 1
        assert ctx["readiness_warnings"]
        assert ctx["products_count"] == 50
        assert ctx["customers_count"] == 20

    def test_company_dashboard_warns_when_no_logo(self, app, mocker):
        tenant = _tenant(1, logo_url="")
        session = mocker.patch("utils.owner_panel.db.session")
        session.get.return_value = tenant
        mocker.patch("utils.owner_panel.resolve_tenant_branding", return_value={})
        mocker.patch("utils.owner_panel.branding_path_warnings", return_value=[])
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.first.return_value = (0, Decimal("0"))
        session.query.return_value = sales_q
        prod_q = MagicMock()
        prod_q.filter_by.return_value.count.return_value = 0
        mocker.patch("models.Product.query", prod_q)
        cust_q = MagicMock()
        cust_q.filter_by.return_value.count.return_value = 0
        mocker.patch("models.Customer.query", cust_q)
        user_q = MagicMock()
        user_q.filter.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.User.query", user_q)
        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 0
        mocker.patch("utils.owner_panel.Branch.query", branch_q)
        mocker.patch(
            "services.backup_service.BackupService.list_backups", return_value=[]
        )
        wh_q = MagicMock()
        wh_q.filter_by.return_value.order_by.return_value.all.return_value = []
        mocker.patch("utils.owner_panel.Warehouse.query", wh_q)
        from utils.owner_panel import build_company_dashboard_context

        with app.app_context():
            ctx = build_company_dashboard_context(1)
        assert any("logo" in w.lower() for w in ctx["readiness_warnings"])

    def test_evaluate_skips_rows_without_user_warning(self):
        from utils.owner_panel import evaluate_tenant_user_warnings

        rows = [{"tenant": _tenant(), "warn_no_users": False, "warn_slug": "x"}]
        fails, warns = evaluate_tenant_user_warnings(rows)
        assert fails == [] and warns == []

    def test_commission_import_failure(self, app, mocker):
        tenant = _tenant(1)
        mocker.patch("utils.owner_panel.db.session.get", return_value=tenant)
        mocker.patch("utils.owner_panel.resolve_tenant_branding", return_value={})
        mocker.patch("utils.owner_panel.branding_path_warnings", return_value=[])
        sales_result = (1, Decimal("100"))
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.first.return_value = sales_result
        cogs_q = MagicMock()
        cogs_q.select_from.return_value.join.return_value.filter.return_value = cogs_q
        cogs_q.scalar.return_value = Decimal("0")
        session = mocker.patch("utils.owner_panel.db.session")
        session.query.side_effect = lambda *m: (
            cogs_q if getattr(m[0], "__name__", "") == "SaleLine" else sales_q
        )
        prod_q = MagicMock()
        prod_q.filter_by.return_value.count.return_value = 1
        mocker.patch("models.Product.query", prod_q)
        cust_q = MagicMock()
        cust_q.filter_by.return_value.count.return_value = 1
        mocker.patch("models.Customer.query", cust_q)
        user_q = MagicMock()
        user_q.filter.return_value.count.return_value = 1
        mocker.patch("utils.owner_panel.User.query", user_q)
        branch_q = MagicMock()
        branch_q.filter_by.return_value.count.return_value = 1
        mocker.patch("utils.owner_panel.Branch.query", branch_q)
        mocker.patch(
            "services.backup_service.BackupService.list_backups", return_value=[]
        )
        wh_q = MagicMock()
        wh_q.filter_by.return_value.order_by.return_value.all.return_value = []
        mocker.patch("utils.owner_panel.Warehouse.query", wh_q)

        real_import = __import__

        def _raise_import(name, *a, **k):
            if name == "models.partner_commission":
                raise ImportError("no commission")
            return real_import(name, *a, **k)

        mocker.patch("builtins.__import__", side_effect=_raise_import)
        from utils.owner_panel import build_company_dashboard_context

        with app.app_context():
            ctx = build_company_dashboard_context(1)
        assert ctx["month_commissions"] == 0.0


class TestTenantsWithoutUsersAllowlist:
    def test_parses_env(self, monkeypatch):
        monkeypatch.setenv("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS", "a, B ,c")
        from utils.owner_panel import tenants_without_users_allowlist

        assert tenants_without_users_allowlist() == {"a", "b", "c"}


class TestEvaluateTenantUserWarnings:
    def test_allowlist_produces_warn_not_fail(self, monkeypatch):
        monkeypatch.setenv("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS", "nasrallah")
        from utils.owner_panel import evaluate_tenant_user_warnings

        rows = [
            {
                "tenant": _tenant(slug="nasrallah"),
                "warn_no_users": True,
                "warn_slug": "nasrallah",
            }
        ]
        fails, warns = evaluate_tenant_user_warnings(rows)
        assert len(fails) == 0
        assert len(warns) == 1

    def test_non_allowlisted_is_fail(self):
        from utils.owner_panel import evaluate_tenant_user_warnings

        rows = [
            {
                "tenant": _tenant(slug="orphan"),
                "warn_no_users": True,
                "warn_slug": "orphan",
            }
        ]
        fails, warns = evaluate_tenant_user_warnings(rows)
        assert len(fails) == 1

    def test_inactive_tenant_skipped(self):
        from utils.owner_panel import evaluate_tenant_user_warnings

        rows = [
            {
                "tenant": _tenant(is_active=False),
                "warn_no_users": True,
                "warn_slug": "x",
            }
        ]
        fails, warns = evaluate_tenant_user_warnings(rows)
        assert fails == [] and warns == []
