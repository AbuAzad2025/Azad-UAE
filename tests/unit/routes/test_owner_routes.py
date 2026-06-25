from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import make_response
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, unauthenticated_client


def _mock_tenant(**kwargs):
    tenant = MagicMock()
    tenant.id = kwargs.get("id", 1)
    tenant.name = kwargs.get("name", "Test Tenant")
    tenant.name_ar = kwargs.get("name_ar", "تينانت")
    tenant.name_en = kwargs.get("name_en", "Test Tenant")
    tenant.slug = kwargs.get("slug", "test-tenant")
    tenant.is_active = kwargs.get("is_active", True)
    tenant.is_suspended = kwargs.get("is_suspended", False)
    tenant.default_currency = kwargs.get("default_currency", "AED")
    tenant.enable_tax = kwargs.get("enable_tax", False)
    tenant.vat_country = kwargs.get("vat_country", "AE")
    tenant.default_tax_rate = kwargs.get("default_tax_rate", Decimal("5"))
    tenant.prices_include_vat = kwargs.get("prices_include_vat", False)
    tenant.logo_url = kwargs.get("logo_url", "")
    tenant.updated_at = None
    return tenant


def _mock_user_entity(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.username = kwargs.get("username", "panel-user")
    user.email = kwargs.get("email", "user@test.com")
    user.full_name = kwargs.get("full_name", "Panel User")
    user.is_owner = kwargs.get("is_owner", False)
    user.is_active = kwargs.get("is_active", True)
    user.tenant_id = kwargs.get("tenant_id", 1)
    user.role_id = kwargs.get("role_id", 2)
    user.branch_id = kwargs.get("branch_id", None)
    user.is_manager.return_value = kwargs.get("is_manager", True)
    user.is_admin.return_value = kwargs.get("is_admin", True)
    user.check_password.return_value = kwargs.get("password_ok", True)
    return user


def _mock_role(slug="seller", level=10):
    role = MagicMock()
    role.slug = slug
    role.is_active = True
    role.id = 2
    return role


def _mock_card():
    card = MagicMock()
    card.id = 1
    card.customer_id = 5
    card.last_four = "4242"
    card.to_dict.return_value = {"id": 1, "last_four": "4242"}
    return card


def _mock_branch():
    branch = MagicMock()
    branch.id = 1
    branch.name = "Main"
    branch.code = "BR01"
    branch.tenant_id = 1
    return branch


def _dashboard_db_query():
    q = _chain_query(scalar=Decimal("0"), count=0, all=[])
    triple = (0, Decimal("0"), Decimal("0"))
    pair = (Decimal("0"), 0)
    inv_pair = (Decimal("0"), Decimal("0"))
    q.first.return_value = triple
    q.filter.return_value.first.return_value = triple
    q.filter.return_value.scalar.return_value = Decimal("0")
    q.scalar.return_value = Decimal("0")
    q.join.return_value.filter.return_value.distinct.return_value.count.return_value = 0
    q.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    q.outerjoin.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    q.filter.return_value.group_by.return_value.all.return_value = []
    q.select_from.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal("0")
    return q


def _model_query(**terminals):
    entity = terminals.get("entity")
    q = _chain_query(**terminals)
    fb = q.filter_by.return_value
    fb.count.return_value = terminals.get("count", 0)
    fb.first.return_value = terminals.get("first")
    fb.all.return_value = terminals.get("all", [])
    fb.order_by.return_value.all.return_value = terminals.get("all", [])
    fb.filter.return_value.count.return_value = terminals.get("count", 0)
    fb.filter.return_value.order_by.return_value.limit.return_value.all.return_value = terminals.get("all", [])
    q.filter.return_value.distinct.return_value.count.return_value = terminals.get("count", 0)
    q.filter.return_value.count.return_value = terminals.get("count", 0)
    q.filter.return_value.delete.return_value = terminals.get("deleted", 0)
    q.order_by.return_value.limit.return_value.all.return_value = terminals.get("all", [])
    q.join.return_value.filter.return_value = q.filter.return_value
    q.get_or_404.return_value = entity
    if entity is None and terminals.get("missing"):
        q.get_or_404.side_effect = NotFound()
    return q


def _execute_result(rows=None, columns=None):
    result = MagicMock()
    result.fetchall.return_value = rows or []
    result.keys.return_value = columns or ["id"]
    result.scalar.return_value = 0
    return result


def _inspector():
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["customers", "products", "sales"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "name"}]
    inspector.get_indexes.return_value = []
    inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    return inspector


def _tenant_query(**terminals):
    q = _model_query(**terminals)

    def get_or_404(pk):
        return _mock_tenant(id=pk)

    q.get_or_404.side_effect = get_or_404
    return q


def _service_contexts():
    return {
        "users_list": {
            "users": [],
            "stats": {},
            "active_tenant_id": 1,
            "tenants": [],
        },
        "roles": {
            "roles": [],
            "permissions": [],
            "perm_categories": [],
            "role_user_counts": {},
        },
        "audit": ([], MagicMock(items=[]), {}, []),
        "activity": {
            "recent_audits": [],
            "active_users": [],
            "recent_sales": [],
            "stats": {},
        },
        "performance": {"cpu": 0},
        "error_logs": ([], MagicMock(items=[]), [], [], {}),
        "integrations": {},
        "backups_list": {
            "backups": [],
            "stats": {},
            "schedule_settings": {},
            "schedule_state": {},
            "backup_dir": "/tmp",
            "pg_tools": {},
            "tenants": [],
            "branches": [],
            "stores": [],
            "is_platform_owner": True,
            "now": "2025-01-01",
        },
        "financial_advanced": {"months_data": [], "kpis": {}},
        "tenants_list": {
            "tenants": [],
            "user_counts": {},
            "branch_counts": {},
            "store_counts": {},
        },
        "db_stats": ([], 0),
        "health": {"status": "ok"},
        "company_dashboard": {"stats": {}, "kpis": {}},
    }


@contextmanager
def _owner_route_patches(**overrides):
    tenant = overrides.get("tenant") or _mock_tenant()
    user_entity = overrides.get("user_entity") or _mock_user_entity()
    card = overrides.get("card") or _mock_card()
    role = overrides.get("role") or _mock_role()
    settings = MagicMock()
    settings.owner_whitelist_ips = []
    settings.default_currency = "AED"
    settings.auto_update_rates = False
    settings.get_custom_setting.return_value = ""
    settings.set_custom_setting = MagicMock()
    invoice_settings = MagicMock()
    invoice_settings.enable_qr_code = False
    invoice_settings.company_name_ar = "شركة"
    vault = MagicMock()
    vault.is_locked = False
    ctx = _service_contexts()
    execute_result = _execute_result()
    backup_payload = {"filename": "backup.sql.gz", "size_mb": 1.2, "valid": True, "format": "sql"}
    mock_db = MagicMock()

    def _session_get(model, pk):
        model_name = getattr(model, "__name__", str(model))
        if model_name == "User":
            return _mock_user_entity(id=pk)
        if model_name == "Role":
            return role
        if model_name == "Tenant":
            return _mock_tenant(id=pk)
        if model_name == "TenantStore":
            store = MagicMock()
            store.id = pk
            store.is_enabled = True
            store.platform_disabled = False
            return store
        if model_name == "Warehouse":
            warehouse = MagicMock()
            warehouse.id = pk
            warehouse.allow_negative_inventory = False
            return warehouse
        return _mock_tenant(id=pk)

    mock_db.session.query.side_effect = lambda *a, **k: _dashboard_db_query()
    mock_db.session.get.side_effect = _session_get
    mock_db.session.execute.return_value = execute_result
    mock_db.engine = MagicMock()

    stack = ExitStack()
    patches = [
        ("routes.owner.render_template", patch("routes.owner.render_template", return_value="ok")),
        ("routes.owner.db", patch("routes.owner.db", mock_db)),
        ("routes.owner.inspect", patch("routes.owner.inspect", return_value=_inspector())),
        ("routes.owner._known_tables_map", patch("routes.owner._known_tables_map", return_value={"customers": "customers", "products": "products", "sales": "sales"})),
        ("routes.owner.get_visible_products_query", patch("routes.owner.get_visible_products_query", return_value=_model_query(count=0, all=[]))),
        ("routes.owner.get_active_tenant_id", patch("routes.owner.get_active_tenant_id", return_value=1)),
        ("utils.decorators.branch_scope_id", patch("utils.decorators.branch_scope_id", return_value=None)),
        ("routes.owner.role_level_for_user", patch("routes.owner.role_level_for_user", return_value=100)),
        ("routes.owner.role_level_for", patch("routes.owner.role_level_for", return_value=10)),
        ("routes.owner.role_requires_branch", patch("routes.owner.role_requires_branch", return_value=False)),
        ("routes.owner.User.query", patch("routes.owner.User.query", new=_model_query(entity=user_entity))),
        ("routes.owner.Customer.query", patch("routes.owner.Customer.query", new=_model_query())),
        ("routes.owner.Product.query", patch("routes.owner.Product.query", new=_model_query(all=[]))),
        ("routes.owner.Sale.query", patch("routes.owner.Sale.query", new=_model_query())),
        ("routes.owner.Purchase.query", patch("routes.owner.Purchase.query", new=_model_query())),
        ("routes.owner.Payment.query", patch("routes.owner.Payment.query", new=_model_query())),
        ("routes.owner.Receipt.query", patch("routes.owner.Receipt.query", new=_model_query())),
        ("routes.owner.AuditLog.query", patch("routes.owner.AuditLog.query", new=_model_query(all=[]))),
        ("routes.owner.ArchivedRecord.query", patch("routes.owner.ArchivedRecord.query", new=_model_query())),
        ("routes.owner.CardVault.query", patch("routes.owner.CardVault.query", new=_model_query(entity=card))),
        ("routes.owner.Tenant.query", patch("routes.owner.Tenant.query", new=_tenant_query(all=[tenant], first=None))),
        ("routes.owner.Branch.query", patch("routes.owner.Branch.query", new=_model_query(all=[_mock_branch()]))),
        ("routes.owner.Warehouse.query", patch("routes.owner.Warehouse.query", new=_model_query(all=[]))),
        ("routes.owner.LoginHistory.query", patch("routes.owner.LoginHistory.query", new=_model_query(all=[]))),
        ("routes.owner.SecurityAlert.query", patch("routes.owner.SecurityAlert.query", new=_model_query(all=[]))),
        ("routes.owner.APIKey.query", patch("routes.owner.APIKey.query", new=_model_query(all=[]))),
        ("routes.owner.Expense.query", patch("routes.owner.Expense.query", new=_model_query())),
        ("models.Donation.query", patch("models.Donation.query", new=_model_query())),
        ("models.exchange_rate_record.ExchangeRateRecord.query", patch("models.ExchangeRateRecord.query", new=_model_query(all=[]))),
        ("routes.owner.Tenant.get_current", patch("routes.owner.Tenant.get_current", return_value=tenant)),
        ("routes.owner.SystemSettings.get_current", patch("routes.owner.SystemSettings.get_current", return_value=settings)),
        ("routes.owner.InvoiceSettings.get_active", patch("routes.owner.InvoiceSettings.get_active", return_value=invoice_settings)),
        ("models.payment_vault.PaymentVault.get_platform_vault", patch("models.PaymentVault.get_platform_vault", return_value=vault)),
        ("utils.master_login.master_login_status", patch("utils.master_login.master_login_status", return_value={"enabled": True})),
        ("utils.master_login.build_today_master_cleartext", patch("utils.master_login.build_today_master_cleartext", return_value="today-secret")),
        ("services.logging_core.LoggingCore.get_db_stats_context", patch("services.logging_core.LoggingCore.get_db_stats_context", return_value=ctx["db_stats"])),
        ("services.logging_core.LoggingCore.get_audit_logs", patch("services.logging_core.LoggingCore.get_audit_logs", return_value=ctx["audit"])),
        ("services.logging_core.LoggingCore.get_activity_context", patch("services.logging_core.LoggingCore.get_activity_context", return_value=ctx["activity"])),
        ("services.logging_core.LoggingCore.get_performance_metrics_data", patch("services.logging_core.LoggingCore.get_performance_metrics_data", return_value=ctx["performance"])),
        ("services.logging_core.LoggingCore.get_error_logs", patch("services.logging_core.LoggingCore.get_error_logs", return_value=ctx["error_logs"])),
        ("services.logging_core.LoggingCore.mark_error_resolved", patch("services.logging_core.LoggingCore.mark_error_resolved", return_value=True)),
        ("services.logging_core.LoggingCore.export_error_logs", patch("services.logging_core.LoggingCore.export_error_logs", return_value=(b"{}", "application/json", "errors.json"))),
        ("services.archive_service.ArchiveService.get_archived_records_query", patch("services.archive_service.ArchiveService.get_archived_records_query", return_value=_chain_query(all=[]))),
        ("services.user_service.UserService.get_users_list_context", patch("services.user_service.UserService.get_users_list_context", return_value=ctx["users_list"])),
        ("services.role_service.RoleService.get_roles_permissions_context", patch("services.role_service.RoleService.get_roles_permissions_context", return_value=ctx["roles"])),
        ("services.financial_service.FinancialService.financial_overview", patch("services.financial_service.FinancialService.financial_overview", return_value="ok")),
        ("services.financial_service.FinancialService.get_financial_dashboard_advanced_context", patch("services.financial_service.FinancialService.get_financial_dashboard_advanced_context", return_value=ctx["financial_advanced"])),
        ("services.integration_service.IntegrationService.get_integrations_context", patch("services.integration_service.IntegrationService.get_integrations_context", return_value=ctx["integrations"])),
        ("services.backup_service.BackupService.list_backups", patch("services.backup_service.BackupService.list_backups", return_value=[backup_payload])),
        ("services.backup_service.BackupService.get_list_backups_context", patch("services.backup_service.BackupService.get_list_backups_context", return_value=ctx["backups_list"])),
        ("services.backup_service.BackupService.create_backup", patch("services.backup_service.BackupService.create_backup", return_value=backup_payload)),
        ("services.backup_service.BackupService.get_schedule_settings", patch("services.backup_service.BackupService.get_schedule_settings", return_value={})),
        ("services.backup_service.BackupService.get_schedule_state", patch("services.backup_service.BackupService.get_schedule_state", return_value={})),
        ("services.backup_service.BackupService.get_backup_stats", patch("services.backup_service.BackupService.get_backup_stats", return_value={})),
        ("services.backup_service.BackupService.save_schedule_settings", patch("services.backup_service.BackupService.save_schedule_settings")),
        ("services.backup_service.BackupService.sanitize_filename", patch("services.backup_service.BackupService.sanitize_filename", side_effect=lambda x: x)),
        ("services.backup_service.BackupService.user_may_access_backup", patch("services.backup_service.BackupService.user_may_access_backup", return_value=True)),
        ("services.backup_service.BackupService.get_backup_info", patch("services.backup_service.BackupService.get_backup_info", return_value={"filename": "backup.sql.gz"})),
        ("services.backup_service.BackupService.verify_backup", patch("services.backup_service.BackupService.verify_backup", return_value={"valid": True, "format": "sql", "errors": []})),
        ("services.backup_service.BackupService.prepare_restore", patch("services.backup_service.BackupService.prepare_restore", return_value={"ok": True, "commands": []})),
        ("services.health_service.HealthCheckService.get_health_data", patch("services.health_service.HealthCheckService.get_health_data", return_value=ctx["health"])),
        ("services.tenant_service.TenantService.get_tenants_list_context", patch("services.tenant_service.TenantService.get_tenants_list_context", return_value=ctx["tenants_list"])),
        ("services.store_payment_method_service.StorePaymentMethodService.ensure_defaults", patch("services.store_payment_method_service.StorePaymentMethodService.ensure_defaults")),
        ("services.store_payment_method_service.StorePaymentMethodService.list_all", patch("services.store_payment_method_service.StorePaymentMethodService.list_all", return_value=[])),
        ("services.store_service.StoreService.stores_globally_enabled", patch("services.store_service.StoreService.stores_globally_enabled", return_value=True)),
        ("services.store_service.StoreService.is_store_publicly_available", patch("services.store_service.StoreService.is_store_publicly_available", return_value=True)),
        ("services.store_service.StoreService.set_platform_disabled", patch("services.store_service.StoreService.set_platform_disabled")),
        ("services.currency_service.CurrencyService.get_all_rates", patch("services.currency_service.CurrencyService.get_all_rates", return_value=[])),
        ("services.exchange_rate_service.ExchangeRateService.save_manual_rate", patch("services.exchange_rate_service.ExchangeRateService.save_manual_rate", return_value={"ok": True})),
        ("services.analytics_service.AnalyticsService.get_sales_insights", patch("services.analytics_service.AnalyticsService.get_sales_insights", return_value={})),
        ("services.analytics_service.AnalyticsService.get_customer_insights", patch("services.analytics_service.AnalyticsService.get_customer_insights", return_value=[])),
        ("services.analytics_service.AnalyticsService.get_product_performance", patch("services.analytics_service.AnalyticsService.get_product_performance", return_value=[])),
        ("services.analytics_service.AnalyticsService.get_forecasting_data", patch("services.analytics_service.AnalyticsService.get_forecasting_data", return_value=([], []))),
        ("utils.owner_panel.build_platform_overview", patch("utils.owner_panel.build_platform_overview", return_value={})),
        ("utils.owner_panel.build_tenant_management_rows", patch("utils.owner_panel.build_tenant_management_rows", return_value=[])),
        ("utils.owner_panel.build_branding_overview_rows", patch("utils.owner_panel.build_branding_overview_rows", return_value=[])),
        ("utils.owner_panel.build_system_health_summary", patch("utils.owner_panel.build_system_health_summary", return_value={})),
        ("utils.owner_panel.build_company_dashboard_context", patch("utils.owner_panel.build_company_dashboard_context", return_value=ctx["company_dashboard"])),
        ("utils.tenant_branding.get_print_header_context", patch("utils.tenant_branding.get_print_header_context", return_value={})),
        ("utils.number_to_arabic.number_to_arabic_words", patch("utils.number_to_arabic.number_to_arabic_words", return_value="كلمات")),
        ("utils.qr_generator.generate_qr_data_url", patch("utils.qr_generator.generate_qr_data_url", return_value="")),
        ("utils.ai_access.get_tenant_ai_level", patch("utils.ai_access.get_tenant_ai_level", return_value="execute")),
        ("utils.ai_access.set_tenant_ai_level", patch("utils.ai_access.set_tenant_ai_level", return_value="execute")),
        ("utils.auth_helpers.enforce_company_user_tenant", patch("utils.auth_helpers.enforce_company_user_tenant")),
        ("utils.auth_helpers.user_may_have_null_tenant", patch("utils.auth_helpers.user_may_have_null_tenant", return_value=False)),
        ("utils.password_validator.PasswordValidator.validate", patch("utils.password_validator.PasswordValidator.validate", return_value=(True, []))),
        ("extensions.cache.clear", patch("extensions.cache.clear")),
        ("models.api_key.APIKey.generate_key", patch("models.api_key.APIKey.generate_key", return_value="generated-key")),
        ("routes.owner.IntegrationSettings.get_service_config", patch("routes.owner.IntegrationSettings.get_service_config", return_value=MagicMock())),
    ]
    for name, p in patches:
        stack.enter_context(p)
    stack.enter_context(patch("models.Role.query", new=_model_query(all=[role])))
    if overrides.get("role_query"):
        stack.enter_context(patch("models.Role.query", new=overrides["role_query"]))
    yield stack


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp, {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"})
    with _owner_route_patches():
        yield app.test_client()


OWNER_GET_ROUTES = [
    "/owner/master-login-info",
    "/owner/",
    "/owner/dashboard",
    "/owner/system-stats",
    "/owner/audit-logs",
    "/owner/archived",
    "/owner/users-list",
    "/owner/users/create",
    "/owner/users/1/edit",
    "/owner/users/1/profile",
    "/owner/roles-permissions",
    "/owner/financial-overview",
    "/owner/config",
    "/owner/cards-vault",
    "/owner/database-tools",
    "/owner/integrations",
    "/owner/backups/list",
    "/owner/sql-console",
    "/owner/scheduled-backups",
    "/owner/reports",
    "/owner/company-info",
    "/owner/developer-settings",
    "/owner/system-config",
    "/owner/store-payment-methods",
    "/owner/tenant-stores",
    "/owner/tenant-ai",
    "/owner/invoice-settings",
    "/owner/preview-invoice/modern",
    "/owner/system-health",
    "/owner/activity-monitor",
    "/owner/login-history",
    "/owner/performance-metrics",
    "/owner/security-alerts",
    "/owner/ip-whitelist",
    "/owner/api-keys",
    "/owner/financial-dashboard-advanced",
    "/owner/tax-settings",
    "/owner/currency-settings",
    "/owner/exchange-rates",
    "/owner/payment-gateways",
    "/owner/email-settings",
    "/owner/sms-settings",
    "/owner/whatsapp-settings",
    "/owner/notification-templates",
    "/owner/verify-backups",
    "/owner/data-cleanup",
    "/owner/import-export-tools",
    "/owner/sales-insights",
    "/owner/customer-insights",
    "/owner/product-performance",
    "/owner/forecasting",
    "/owner/tenants",
    "/owner/tenants/create",
    "/owner/error-audit-logs",
]


@pytest.mark.parametrize("path", OWNER_GET_ROUTES)
def test_owner_get_routes_return_ok(owner_client, path):
    resp = owner_client.get(path)
    assert resp.status_code in (200, 302)


class TestOwnerAuth:
    def test_unauthenticated_returns_404(self, app_factory):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        client = app.test_client()
        with _owner_route_patches(), unauthenticated_client(client):
            resp = client.get("/owner/dashboard")
            assert resp.status_code == 404

    def test_non_owner_returns_404(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        app = app_factory(owner_bp)
        client = app.test_client()
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = client.get("/owner/dashboard")
            assert resp.status_code == 404


class TestCompanyDashboard:
    def test_company_dashboard_with_company_admin(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        mock_user.is_super_admin.return_value = True
        mock_user.tenant_id = 1
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
            patch("services.logging_core.LoggingCore.log_audit"),
        ]
        app = app_factory(owner_bp)
        client = app.test_client()
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = client.get("/owner/company-dashboard")
            assert resp.status_code == 200


class TestOwnerPostRoutes:
    def test_backup_now_json_success(self, owner_client):
        resp = owner_client.post(
            "/owner/backup-now",
            json={"description": "unit test backup"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "filename" in data

    def test_backup_now_form_redirect(self, owner_client):
        resp = owner_client.post(
            "/owner/backup-now",
            data={"description": "form backup"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_clear_cache_redirects(self, owner_client):
        resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_tenant_create_get(self, owner_client):
        resp = owner_client.get("/owner/tenants/create")
        assert resp.status_code == 200

    def test_tenant_create_post_success(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة جديدة",
                "name_en": "New Co",
                "slug": "new-co",
                "default_currency": "AED",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_create_post_missing_fields(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/create",
            data={"name_ar": "", "slug": ""},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_sql_console_get(self, owner_client):
        resp = owner_client.get("/owner/sql-console")
        assert resp.status_code == 200

    def test_sql_console_post_valid_select(self, owner_client):
        resp = owner_client.post(
            "/owner/sql-console",
            data={"sql_query": "SELECT 1"},
        )
        assert resp.status_code == 200

    def test_sql_console_post_invalid_query(self, owner_client):
        resp = owner_client.post(
            "/owner/sql-console",
            data={"sql_query": "DELETE FROM users"},
        )
        assert resp.status_code == 200

    def test_execute_query_empty(self, owner_client):
        resp = owner_client.post("/owner/execute-query", data={"query": ""})
        assert resp.status_code == 400
        assert "empty" in resp.get_json()["error"].lower()

    def test_execute_query_invalid_mutation(self, owner_client):
        resp = owner_client.post(
            "/owner/execute-query",
            data={"query": "UPDATE users SET username='x'"},
        )
        assert resp.status_code == 400

    def test_execute_query_valid_select(self, owner_client):
        resp = owner_client.post(
            "/owner/execute-query",
            data={"query": "SELECT id FROM users"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_api_tenant_toggle_status(self, owner_client):
        resp = owner_client.post(
            "/owner/api/tenant/2/toggle-status",
            json={},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_api_tenant_update_package(self, owner_client):
        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"field": "max_users", "value": 10},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_api_tenant_update_package_invalid_field(self, owner_client):
        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"field": "bad_field", "value": 1},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_backup_info_json(self, owner_client):
        resp = owner_client.get("/owner/backups/info/backup.sql.gz")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_verify_backup_post(self, owner_client):
        resp = owner_client.post("/owner/backups/verify/backup.sql.gz")
        assert resp.status_code == 200

    def test_integrations_update_whatsapp(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/whatsapp",
                data={"enabled": "1", "api_token": "tok"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_user_create_post_validation(self, owner_client):
        resp = owner_client.post(
            "/owner/users/create",
            data={"username": "", "password": ""},
        )
        assert resp.status_code == 200

    def test_cards_vault_view(self, owner_client):
        resp = owner_client.get("/owner/cards-vault/1/view")
        assert resp.status_code == 200

    def test_owner_root_redirects(self, owner_client):
        resp = owner_client.get("/owner/", follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestOwnerExtendedCoverage:
    def test_dashboard_platform_mode(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        branch_row = MagicMock()
        branch_row.id = 1
        branch_row.name = "B1"
        branch_row.code = "B1"
        branch_row.tenant_id = 2
        branch_row.sale_count = 1
        branch_row.sale_total = Decimal("100")
        branch_row.sale_month = Decimal("50")
        db_q = _dashboard_db_query()
        db_q.outerjoin.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [branch_row]
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner.get_active_tenant_id", return_value=None), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.query.side_effect = lambda *a, **k: db_q
            mock_db.session.get.side_effect = lambda model, pk: _mock_tenant(id=pk)
            mock_db.engine = MagicMock()
            resp = app.test_client().get("/owner/dashboard")
            assert resp.status_code == 200

    def test_dashboard_with_branch_scope(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        branch = _mock_branch()
        visible_q = _model_query(count=1, all=[MagicMock(visible_stock=0, min_stock_alert=5, current_stock=0)])
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.decorators.branch_scope_id", return_value=2), \
             patch("routes.owner.get_visible_products_query", return_value=visible_q), \
             patch("routes.owner.Branch.query", new=_model_query(all=[branch])):
            resp = app.test_client().get("/owner/dashboard")
            assert resp.status_code == 200

    def test_system_stats_failure_redirect(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("services.logging_core.LoggingCore.get_db_stats_context", side_effect=RuntimeError("db fail")):
            resp = app.test_client().get("/owner/system-stats", follow_redirects=False)
            assert resp.status_code in (302, 303)

    def test_cards_vault_with_customer_filter(self, owner_client):
        resp = owner_client.get("/owner/cards-vault?customer=5")
        assert resp.status_code == 200

    def test_login_history_with_filters(self, owner_client):
        resp = owner_client.get("/owner/login-history?user_id=1&success=true")
        assert resp.status_code == 200

    def test_security_alerts_with_severity(self, owner_client):
        resp = owner_client.get("/owner/security-alerts?severity=high")
        assert resp.status_code == 200

    def test_financial_overview_platform_param(self, owner_client):
        resp = owner_client.get("/owner/financial-overview?_platform=1")
        assert resp.status_code == 200

    def test_backup_now_failure_json(self, owner_client):
        with patch("services.backup_service.BackupService.create_backup", return_value=None):
            resp = owner_client.post("/owner/backup-now", json={})
        assert resp.status_code == 400

    def test_create_scoped_backup_system(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "system", "description": "scoped"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_create_scoped_backup_tenant_missing_id(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "tenant"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_create_scoped_backup_invalid_scope(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "invalid"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_create_scoped_backup_branch(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": "2", "branch_id": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_create_scoped_backup_store_missing(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "store", "tenant_id": "2"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_backup_info_not_found(self, owner_client):
        with patch("services.backup_service.BackupService.get_backup_info", return_value=None):
            resp = owner_client.get("/owner/backups/info/missing.sql.gz")
        assert resp.status_code == 404

    def test_backup_info_denied(self, owner_client):
        with patch("services.backup_service.BackupService.user_may_access_backup", return_value=False):
            resp = owner_client.get("/owner/backups/info/denied.sql.gz")
        assert resp.status_code == 400

    def test_prepare_restore_get(self, owner_client):
        resp = owner_client.get("/owner/backups/prepare-restore/backup.sql.gz")
        assert resp.status_code in (200, 302)

    def test_prepare_restore_json(self, owner_client):
        resp = owner_client.get("/owner/backups/prepare-restore/backup.sql.gz?format=json")
        assert resp.status_code == 200

    def test_prepare_restore_post(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/prepare-restore/backup.sql.gz",
            data={"target_tenant_id": "2", "remap": "1"},
        )
        assert resp.status_code == 200

    def test_scheduled_backups_post(self, owner_client):
        resp = owner_client.post(
            "/owner/scheduled-backups",
            data={"enabled": "on", "frequency": "daily", "backup_time": "03:00", "keep_count": "3"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_integrations_update_email(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/email",
                data={"enabled": "1", "smtp_host": "smtp.test.com"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_integrations_update_redis(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/redis",
                data={"redis_host": "localhost"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_integrations_update_currency_api(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/currency_api",
                data={"api_key": "key"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_integrations_update_error(self, owner_client):
        with patch("routes.owner.IntegrationSettings.get_service_config", side_effect=RuntimeError("fail")):
            resp = owner_client.post(
                "/owner/integrations/update/whatsapp",
                data={"enabled": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_clear_cache_failure_with_fallback(self, owner_client):
        cache_mock = MagicMock()
        cache_mock.clear.side_effect = RuntimeError("redis down")
        cache_mock.cache = MagicMock()
        type(cache_mock.cache).__name__ = "RedisCache"
        cache_mock.app = owner_client.application
        cache_mock.init_app = MagicMock()
        with patch("extensions.cache", cache_mock):
            resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_truncate_table_bad_confirm(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "customers", "confirm": "NO"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_truncate_table_success(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "customers", "confirm": "YES_DELETE_ALL"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_truncate_table_blocked(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "users", "confirm": "YES_DELETE_ALL"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_browse_table_valid(self, owner_client):
        resp = owner_client.get("/owner/browse-table/customers")
        assert resp.status_code == 200

    def test_browse_table_invalid(self, owner_client):
        resp = owner_client.get("/owner/browse-table/users", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_edit_table_data(self, owner_client):
        resp = owner_client.get("/owner/edit-table-data/customers")
        assert resp.status_code in (200, 302)

    def test_update_row_success(self, owner_client):
        resp = owner_client.post(
            "/owner/update-row/customers/1",
            json={"name": "updated"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_update_row_no_data(self, owner_client):
        resp = owner_client.post("/owner/update-row/customers/1", json={})
        assert resp.status_code == 400

    def test_update_row_blocked_table(self, owner_client):
        resp = owner_client.post("/owner/update-row/users/1", json={"name": "x"})
        assert resp.status_code == 403

    def test_execute_query_semicolon_rejected(self, owner_client):
        resp = owner_client.post(
            "/owner/execute-query",
            data={"query": "SELECT 1; SELECT 2"},
        )
        assert resp.status_code == 400

    def test_execute_query_db_error(self, owner_client):
        with patch("routes.owner.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("db error")
            mock_db.session.rollback = MagicMock()
            resp = owner_client.post(
                "/owner/execute-query",
                data={"query": "SELECT 1"},
            )
        assert resp.status_code == 400

    def test_company_info_post(self, owner_client):
        resp = owner_client.post(
            "/owner/company-info",
            data={"name_ar": "شركة", "name_en": "Co", "slug": "co"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_developer_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/developer-settings",
            data={"developer_name": "Dev Co"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_system_config_post(self, owner_client):
        resp = owner_client.post(
            "/owner/system-config",
            data={"maintenance_mode": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_invoice_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/invoice-settings",
            data={"company_name_ar": "شركة"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_preview_receipt(self, owner_client):
        resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_tax_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/tax-settings",
            data={"enable_tax": "on", "vat_country": "AE", "default_tax_rate": "5"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tax_settings_no_tenant(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.Tenant.get_current", return_value=None):
            resp = app.test_client().get("/owner/tax-settings", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_currency_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/currency-settings",
            data={"default_currency": "USD", "auto_update_rates": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_exchange_rates_post_save(self, owner_client):
        resp = owner_client.post(
            "/owner/exchange-rates",
            data={"action": "save", "from_currency": "USD", "to_currency": "AED", "rate": "3.67"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_exchange_rates_post_invalid_rate(self, owner_client):
        resp = owner_client.post(
            "/owner/exchange-rates",
            data={"action": "save", "rate": "0"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_payment_gateways_post(self, owner_client):
        resp = owner_client.post(
            "/owner/payment-gateways",
            data={"stripe_publishable_key": "pk_test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_payment_gateways_creates_vault(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        new_vault = MagicMock()
        with _owner_route_patches(), patch("models.PaymentVault.get_platform_vault", return_value=None):
            resp = app.test_client().get("/owner/payment-gateways")
        assert resp.status_code == 200

    def test_email_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/email-settings",
            data={"smtp_server": "smtp.test.com", "smtp_port": "587"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_sms_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/sms-settings",
            data={"sms_provider": "twilio", "sms_enabled": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_whatsapp_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/whatsapp-settings",
            data={"whatsapp_api_url": "https://api.test", "whatsapp_enabled": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_notification_templates_post(self, owner_client):
        resp = owner_client.post(
            "/owner/notification-templates",
            data={"invoice_email_template": "Hello"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_ip_whitelist_post(self, owner_client):
        resp = owner_client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "10.0.0.1", "description": "office"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_ip_whitelist_delete(self, owner_client):
        settings = MagicMock()
        settings.owner_whitelist_ips = [{"ip": "10.0.0.1", "description": "office"}]
        with patch("routes.owner.SystemSettings.get_current", return_value=settings):
            resp = owner_client.post("/owner/ip-whitelist/0/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_api_keys_post(self, owner_client):
        resp = owner_client.post(
            "/owner/api-keys",
            data={"name": "test", "service": "api"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_api_keys_toggle(self, owner_client):
        key = MagicMock()
        key.is_active = True
        with patch("routes.owner.APIKey.query") as key_query:
            key_query.get_or_404.return_value = key
            resp = owner_client.post("/owner/api-keys/1/toggle", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_security_alert_resolve(self, owner_client):
        alert = MagicMock()
        with patch("routes.owner.SecurityAlert.query") as alert_query:
            alert_query.get_or_404.return_value = alert
            resp = owner_client.post("/owner/security-alerts/1/resolve", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_data_cleanup_post_logs(self, owner_client):
        resp = owner_client.post(
            "/owner/data-cleanup",
            data={"days": "30", "cleanup_type": "logs"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_data_cleanup_post_missing_type(self, owner_client):
        resp = owner_client.post(
            "/owner/data-cleanup",
            data={"days": "30"},
        )
        assert resp.status_code == 200

    def test_tenant_suspend(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/2/suspend",
            data={"reason": "test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_suspend_default_protected(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/1/suspend",
            data={"reason": "test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_activate(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/2/activate",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_edit_get(self, owner_client):
        resp = owner_client.get("/owner/tenants/2/edit")
        assert resp.status_code == 200

    def test_tenant_edit_post(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/2/edit",
            data={"name_ar": "محدث", "slug": "updated"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_delete_with_users(self, owner_client):
        user_q = _model_query(count=3)
        with patch("routes.owner.User.query", new=user_q):
            resp = owner_client.post("/owner/tenants/2/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_tenant_delete_success(self, owner_client):
        user_q = _model_query(count=0)
        with patch("routes.owner.User.query", new=user_q):
            resp = owner_client.post("/owner/tenants/2/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_tenant_ai_toggle(self, owner_client):
        resp = owner_client.post(
            "/owner/tenant-ai/2/toggle",
            data={"enable_ai": "1", "ai_access_level": "advanced"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_tenant_store_platform_toggle(self, owner_client):
        resp = owner_client.post(
            "/owner/tenant-stores/1/platform-toggle",
            data={"platform_disabled": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_error_audit_resolve(self, owner_client):
        resp = owner_client.post(
            "/owner/error-audit-logs/1/resolve",
            data={"note": "fixed"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_error_audit_export_json(self, owner_client):
        resp = owner_client.get("/owner/error-audit-logs/export?format=json")
        assert resp.status_code == 200

    def test_error_audit_export_invalid(self, owner_client):
        with patch("services.logging_core.LoggingCore.export_error_logs", side_effect=ValueError("bad")):
            resp = owner_client.get("/owner/error-audit-logs/export?format=bad", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_user_create_post_success(self, owner_client):
        role = _mock_role(slug="seller")
        user_q = _model_query(first=None)
        with patch("models.Role.query", new=_model_query(all=[role])), \
             patch("routes.owner.User.query", new=user_q), \
             patch("routes.owner.role_requires_branch", return_value=False):
            resp = owner_client.post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass",
                    "email": "new@test.com",
                    "full_name": "New User",
                    "role_id": "2",
                    "tenant_id": "1",
                    "is_active": "on",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_user_edit_post(self, owner_client):
        role = _mock_role(slug="seller")
        target = _mock_user_entity(id=2)
        with patch("models.Role.query", new=_model_query(all=[role])), \
             patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post(
                "/owner/users/2/edit",
                data={
                    "username": "edited",
                    "email": "e@test.com",
                    "full_name": "Edited",
                    "role_id": "2",
                    "is_active": "on",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_user_delete_self_blocked(self, owner_client, bypass_owner_auth):
        target = _mock_user_entity(id=bypass_owner_auth.id)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/42/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_user_delete_owner_blocked(self, owner_client):
        target = _mock_user_entity(id=9, is_owner=True)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/9/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_user_delete_success(self, owner_client):
        target = _mock_user_entity(id=9, is_owner=False)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/9/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_api_update_tenant_settings(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        mock_user.is_super_admin.return_value = True
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
            patch("services.logging_core.LoggingCore.log_audit"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "prices_include_vat", "value": True},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_api_toggle_warehouse_negative(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        warehouse = MagicMock()
        warehouse.allow_negative_inventory = False
        wh_q = _model_query(first=warehouse)
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
            patch("services.logging_core.LoggingCore.log_audit"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(patch("routes.owner.Warehouse.query", new=wh_q))
            resp = app.test_client().post(
                "/owner/api/toggle-warehouse-negative",
                json={"warehouse_id": 1},
            )
        assert resp.status_code == 200

    def test_api_supervisor_override_success(self, owner_client):
        supervisor = _mock_user_entity(id=5, is_manager=True, is_admin=True, password_ok=True)
        with patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = supervisor
            resp = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "secret", "action": "discount"},
            )
        assert resp.status_code == 200

    def test_api_supervisor_override_bad_password(self, owner_client):
        supervisor = _mock_user_entity(id=5, password_ok=False)
        with patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = supervisor
            resp = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "wrong"},
            )
        assert resp.status_code == 403

    def test_system_health_failure(self, owner_client):
        with patch("services.health_service.HealthCheckService.get_health_data", side_effect=RuntimeError("fail")):
            resp = owner_client.get("/owner/system-health", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_verify_backups_failure(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups", side_effect=RuntimeError("fail")):
            resp = owner_client.get("/owner/verify-backups", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_before_request_ip_guard(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.security_helpers.enforce_owner_ip_if_needed", side_effect=RuntimeError("blocked")):
            with pytest.raises(RuntimeError):
                app.test_client().get("/owner/dashboard")

    def test_restore_backup_target_system(self, owner_client):
        with patch("services.backup_service.BackupService.get_backup_info", return_value={"manifest": {"backup_scope": "system"}}), \
             patch("services.backup_service.BackupService.restore_backup_to_target_db", return_value={"ok": True, "target_db": "test", "masked_host": "localhost"}):
            resp = owner_client.post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={"target_database_url": "postgresql://u:p@localhost/testdb", "restore_confirm": "YES"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_restore_backup_target_scoped(self, owner_client):
        with patch("services.backup_service.BackupService.get_backup_info", return_value={"manifest": {"backup_scope": "tenant"}}), \
             patch("services.backup_service.BackupService.restore_scoped_backup_to_target_db", return_value={"ok": False, "errors": ["fail"]}):
            resp = owner_client.post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={"target_database_url": "postgresql://u:p@localhost/testdb"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_delete_backup_success(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups_for_user", return_value=[{"filename": "backup.sql.gz"}]), \
             patch("services.backup_service.BackupService.delete_backup", return_value=True):
            resp = owner_client.post(
                "/owner/backups/delete",
                data={"filename": "backup.sql.gz"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_delete_backup_missing(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups_for_user", return_value=[]):
            resp = owner_client.post(
                "/owner/backups/delete",
                data={"filename": "missing.sql.gz"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_download_backup(self, owner_client, tmp_path):
        backup_file = tmp_path / "backup.sql.gz"
        backup_file.write_bytes(b"data")
        with patch("services.backup_service.BackupService.BACKUP_DIR", str(tmp_path)), \
             patch("routes.owner.os.path.exists", return_value=True), \
             patch("flask.send_file", return_value=make_response("file", 200)):
            resp = owner_client.get("/owner/backups/download/backup.sql.gz")
        assert resp.status_code == 200

    def test_export_database_sql(self, owner_client, tmp_path):
        with patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=MagicMock(returncode=0, stderr="", stdout="")), \
             patch("routes.owner.os.makedirs"), \
             patch("routes.owner.os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            resp = owner_client.post(
                "/owner/export-database",
                data={"format": "sql"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_export_database_invalid_format(self, owner_client):
        resp = owner_client.post(
            "/owner/export-database",
            data={"format": "xml"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_convert_database_get(self, owner_client):
        resp = owner_client.get("/owner/convert-database")
        assert resp.status_code == 200

    def test_convert_database_post(self, owner_client):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        execute_result = _execute_result(rows=[], columns=["id"])
        with patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.execute.return_value = execute_result
            resp = owner_client.post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/newdb"},
            )
        assert resp.status_code == 200

    def test_store_payment_method_create_get(self, owner_client):
        resp = owner_client.get("/owner/store-payment-methods/create")
        assert resp.status_code == 200

    def test_store_payment_method_create_post(self, owner_client):
        with patch("services.store_payment_method_service.StorePaymentMethodService.create_method"):
            resp = owner_client.post(
                "/owner/store-payment-methods/create",
                data={"code": "bank", "name_ar": "بنك", "name_en": "Bank"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_store_payment_method_edit(self, owner_client):
        method = MagicMock()
        method.id = 1
        method.sort_order = 10
        with patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = method
            resp = owner_client.get("/owner/store-payment-methods/1/edit")
        assert resp.status_code == 200

    def test_store_payment_method_edit_post(self, owner_client):
        method = MagicMock()
        method.id = 1
        method.sort_order = 10
        with patch("routes.owner.db") as mock_db, \
             patch("services.store_payment_method_service.StorePaymentMethodService.update_method"):
            mock_db.session.get.return_value = method
            resp = owner_client.post(
                "/owner/store-payment-methods/1/edit",
                data={"code": "bank", "name_ar": "بنك"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_store_payment_method_toggle(self, owner_client):
        with patch("services.store_payment_method_service.StorePaymentMethodService.toggle_enabled"):
            resp = owner_client.post(
                "/owner/store-payment-methods/1/toggle",
                data={"is_enabled": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_store_payment_method_delete(self, owner_client):
        with patch("services.store_payment_method_service.StorePaymentMethodService.delete_method"):
            resp = owner_client.post(
                "/owner/store-payment-methods/1/delete",
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303)

    def test_export_excel_customers(self, owner_client):
        item = MagicMock()
        item.to_dict.return_value = {"id": 1, "name": "Cust"}
        product_q = _model_query(all=[item])
        with patch("routes.owner.Customer.query", new=product_q), \
             patch("flask.send_file", return_value=make_response(b"xlsx", 200)):
            resp = owner_client.get("/owner/export-excel/customers")
        assert resp.status_code == 200

    def test_export_excel_invalid_table(self, owner_client):
        resp = owner_client.get("/owner/export-excel/invalid", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_user_create_missing_role(self, owner_client):
        role = _mock_role(slug="seller")
        with patch("models.Role.query", new=_model_query(all=[role])):
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "u1", "password": "Str0ng!Pass"},
            )
        assert resp.status_code == 200

    def test_user_create_weak_password(self, owner_client):
        role = _mock_role(slug="seller")
        with patch("models.Role.query", new=_model_query(all=[role])), \
             patch("utils.password_validator.PasswordValidator.validate", return_value=(False, ["short"])):
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "u1", "password": "weak", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_user_create_existing_user(self, owner_client):
        role = _mock_role(slug="seller")
        user_q = _model_query(first=_mock_user_entity())
        with patch("models.Role.query", new=_model_query(all=[role])), \
             patch("routes.owner.User.query", new=user_q):
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "exists", "password": "Str0ng!Pass", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_user_create_with_preselect_tenant(self, owner_client):
        resp = owner_client.get("/owner/users/create?tenant_id=2")
        assert resp.status_code == 200

    def test_api_update_tenant_settings_invalid_field(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("routes.owner.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "unknown", "value": 1},
            )
        assert resp.status_code == 400

    def test_api_update_tenant_settings_not_json(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("routes.owner.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post("/owner/api/update-tenant-settings", data={})
        assert resp.status_code == 400

    def test_database_optimize_post(self, owner_client):
        with patch("routes.owner.db") as mock_db:
            mock_db.session.execute.return_value = MagicMock()
            resp = owner_client.post("/owner/database-optimize", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_invalidate_owner_changes_cache_error(self, owner_client):
        with patch("extensions.cache.clear", side_effect=RuntimeError("cache fail")):
            resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_convert_database_invalid_target(self, owner_client):
        resp = owner_client.post(
            "/owner/convert-database",
            data={"target_db": "mysql"},
        )
        assert resp.status_code == 200

    def test_reports_with_branch_scope(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("utils.decorators.branch_scope_id", return_value=3):
            resp = app.test_client().get("/owner/reports")
        assert resp.status_code == 200

    def test_preview_invoice_with_qr(self, owner_client):
        settings = MagicMock()
        settings.enable_qr_code = True
        settings.company_name_ar = "شركة"
        with patch("routes.owner.InvoiceSettings.get_active", return_value=settings):
            resp = owner_client.get("/owner/preview-invoice/modern")
        assert resp.status_code == 200

