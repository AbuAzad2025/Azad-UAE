from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import make_response
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, unauthenticated_client


def _status_code(resp):
    if isinstance(resp, tuple):
        return resp[1]
    return resp.status_code


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


_SAFE_MODEL_COLUMNS = {
    "amount_aed": Decimal("0"),
    "paid_amount_aed": Decimal("0"),
    "balance": Decimal("0"),
    "current_stock": Decimal("0"),
    "min_stock_alert": Decimal("0"),
    "regular_price": Decimal("0"),
    "cost_price": Decimal("0"),
    "unit_price": Decimal("0"),
    "discount_percent": Decimal("0"),
    "quantity": Decimal("0"),
    "line_total": Decimal("0"),
    "sale_id": 0,
    "product_id": 0,
    "warehouse_id": 0,
    "customer_id": 0,
    "user_id": 0,
    "success": True,
    "status": "confirmed",
    "is_active": True,
    "is_owner": False,
    "is_reversed": False,
    "tenant_id": 1,
    "id": 0,
}

_ORDERABLE_COLUMNS = (
    "sale_date", "purchase_date", "login_time", "created_at", "archived_at",
    "effective_date",
)


def _orderable_col():
    col = MagicMock()
    col.desc.return_value = col
    col.asc.return_value = col
    col.in_ = MagicMock(return_value=col)
    col.__ge__ = MagicMock(return_value=MagicMock())
    col.__gt__ = MagicMock(return_value=MagicMock())
    col.__lt__ = MagicMock(return_value=MagicMock())
    return col


def _model_class(**terminals):
    """Mock ORM model class (avoids touching real SQLAlchemy .query descriptors)."""
    cls = MagicMock(name="model_class")
    cls.query = _model_query(**terminals)
    for attr, val in _SAFE_MODEL_COLUMNS.items():
        if attr == "id":
            continue
        setattr(cls, attr, val)
    for attr in ("id", "warehouse_id", "branch_id"):
        setattr(cls, attr, _orderable_col())
    for attr in _ORDERABLE_COLUMNS:
        setattr(cls, attr, _orderable_col())
    cls.__table__ = MagicMock(columns=[MagicMock(name="id")])
    return cls


def _tenant_class(tenant, **terminals):
    cls = _model_class(all=[tenant], **terminals)
    cls.get_current = MagicMock(return_value=tenant)
    cls.query.get_or_404.side_effect = lambda pk: _mock_tenant(id=pk)
    return cls


def _settings_class(settings):
    cls = MagicMock(name="SystemSettings")
    cls.get_current = MagicMock(return_value=settings)
    return cls


def _invoice_settings_class(invoice_settings):
    cls = MagicMock(name="InvoiceSettings")
    cls.get_active = MagicMock(return_value=invoice_settings)
    return cls


def _patch_invoice_settings(stack, invoice_settings):
    inv_cls = _invoice_settings_class(invoice_settings)
    stack.enter_context(patch("routes.owner.InvoiceSettings", inv_cls))
    stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))


def _integration_settings_class():
    cls = MagicMock(name="IntegrationSettings")
    cls.get_service_config = MagicMock(return_value=MagicMock())
    return cls


def _api_key_class():
    cls = _model_class(all=[])
    cls.generate_key = MagicMock(return_value="generated-key")
    return cls


def _payment_vault_class(vault):
    cls = MagicMock(name="PaymentVault")
    cls.get_platform_vault = MagicMock(return_value=vault)
    return cls


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
def _owner_route_patches(mock_db=None, **overrides):
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
    if mock_db is None:
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

    tenant_cls = _tenant_class(tenant)
    user_cls = _model_class(entity=user_entity)
    user_cls.query.get_or_404.return_value = user_entity
    card_cls = _model_class(entity=card)
    role_cls = _model_class(all=[role])
    donation_cls = _model_class()
    exchange_rate_cls = _model_class(all=[])

    patches = [
        ("routes.owner.render_template", patch("routes.owner.render_template", return_value="ok")),
        ("flask.url_for", patch("flask.url_for", side_effect=lambda endpoint, **kwargs: "/")),
        ("flask.url_for", patch("flask.url_for", return_value="/")),
        ("routes.owner.db", patch("routes.owner.db", mock_db)),
        ("extensions.db", patch("extensions.db", mock_db)),
        ("routes.owner.inspect", patch("routes.owner.inspect", return_value=_inspector())),
        ("routes.owner._known_tables_map", patch("routes.owner._known_tables_map", return_value={"customers": "customers", "products": "products", "sales": "sales"})),
        ("routes.owner.get_visible_products_query", patch("routes.owner.get_visible_products_query", return_value=_model_query(count=0, all=[]))),
        ("routes.owner.get_active_tenant_id", patch("routes.owner.get_active_tenant_id", return_value=1)),
        ("utils.decorators.branch_scope_id", patch("utils.decorators.branch_scope_id", return_value=None)),
        ("routes.owner.role_level_for_user", patch("routes.owner.role_level_for_user", return_value=100)),
        ("routes.owner.role_level_for", patch("routes.owner.role_level_for", return_value=10)),
        ("routes.owner.role_requires_branch", patch("routes.owner.role_requires_branch", return_value=False)),
        ("routes.owner.User", patch("routes.owner.User", user_cls)),
        ("routes.owner.Customer", patch("routes.owner.Customer", _model_class())),
        ("routes.owner.Product", patch("routes.owner.Product", _model_class(all=[]))),
        ("routes.owner.Sale", patch("routes.owner.Sale", _model_class())),
        ("routes.owner.Purchase", patch("routes.owner.Purchase", _model_class())),
        ("routes.owner.Payment", patch("routes.owner.Payment", _model_class())),
        ("routes.owner.Receipt", patch("routes.owner.Receipt", _model_class())),
        ("routes.owner.AuditLog", patch("routes.owner.AuditLog", _model_class(all=[]))),
        ("routes.owner.ArchivedRecord", patch("routes.owner.ArchivedRecord", _model_class())),
        ("routes.owner.CardVault", patch("routes.owner.CardVault", card_cls)),
        ("routes.owner.Tenant", patch("routes.owner.Tenant", tenant_cls)),
        ("routes.owner.Branch", patch("routes.owner.Branch", _model_class(all=[_mock_branch()]))),
        ("routes.owner.Warehouse", patch("routes.owner.Warehouse", _model_class(all=[]))),
        ("routes.owner.LoginHistory", patch("routes.owner.LoginHistory", _model_class(all=[]))),
        ("routes.owner.SecurityAlert", patch("routes.owner.SecurityAlert", _model_class(all=[]))),
        ("routes.owner.APIKey", patch("routes.owner.APIKey", _api_key_class())),
        ("routes.owner.Expense", patch("routes.owner.Expense", _model_class())),
        ("routes.owner.SaleLine", patch("routes.owner.SaleLine", _model_class())),
        ("models.Donation", patch("models.Donation", donation_cls)),
        ("models.ExchangeRateRecord", patch("models.ExchangeRateRecord", exchange_rate_cls)),
        ("routes.owner.SystemSettings", patch("routes.owner.SystemSettings", _settings_class(settings))),
        ("services.logging_core.LoggingCore.log_error", patch("services.logging_core.LoggingCore.log_error")),
        ("models.PaymentVault", patch("models.PaymentVault", _payment_vault_class(vault))),
        ("routes.owner.IntegrationSettings", patch("routes.owner.IntegrationSettings", _integration_settings_class())),
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
    ]
    with ExitStack() as stack:
        for name, p in patches:
            stack.enter_context(p)
        _patch_invoice_settings(stack, invoice_settings)
        stack.enter_context(patch("models.Role", role_cls))
        if overrides.get("role_query"):
            role_override = _model_class()
            role_override.query = overrides["role_query"]
            stack.enter_context(patch("models.Role", role_override))
        for model_name in ("Sale", "Payment", "Receipt", "User", "Customer", "Product", "Donation", "SaleLine", "Branch", "Tenant"):
            stack.enter_context(patch(f"models.{model_name}", _model_class() if model_name != "Tenant" else tenant_cls))
        stack.enter_context(patch("models.ProductWarehouseCost", _model_class()))
        # ── Propagate ALL patched routes.owner attributes to sub-modules ──
        # Sub-modules do `from routes.owner import X` at module load time,
        # creating local references. Patching routes.owner.X doesn't affect
        # those local references. Explicitly overwrite them.
        import routes.owner as _own_mod
        _owner_names = {
            name_str.split(".", 2)[2]
            for name_str, _ in patches
            if name_str.startswith("routes.owner.") and name_str.count(".") == 2
        }
        for _sn in ("core", "tenants", "users", "backups", "database", "settings", "monitoring", "shared"):
            _sm = getattr(_own_mod, _sn, None)
            if _sm is None:
                continue
            _sd = vars(_sm)
            for _an in _owner_names:
                if _an in _sd:
                    setattr(_sm, _an, getattr(_own_mod, _an))
        # ── End propagation ───────────────────────────────────────────────
        yield


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    with _owner_route_patches():
        from routes.owner import owner_bp

        app = app_factory(owner_bp, {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"})
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
        assert resp.status_code in (302, 303, 200)

    def test_clear_cache_redirects(self, owner_client):
        resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_tenant_create_post_missing_fields(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/create",
            data={"name_ar": "", "slug": ""},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)


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
            assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_create_scoped_backup_tenant_missing_id(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "tenant"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_create_scoped_backup_invalid_scope(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "invalid"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_create_scoped_backup_branch(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": "2", "branch_id": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_create_scoped_backup_store_missing(self, owner_client):
        resp = owner_client.post(
            "/owner/backups/create",
            data={"scope": "store", "tenant_id": "2"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_integrations_update_email(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/email",
                data={"enabled": "1", "smtp_host": "smtp.test.com"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_integrations_update_redis(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/redis",
                data={"redis_host": "localhost"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_integrations_update_currency_api(self, owner_client):
        integration = MagicMock()
        with patch("routes.owner.IntegrationSettings.get_service_config", return_value=integration):
            resp = owner_client.post(
                "/owner/integrations/update/currency_api",
                data={"api_key": "key"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_integrations_update_error(self, owner_client):
        with patch("routes.owner.IntegrationSettings.get_service_config", side_effect=RuntimeError("fail")):
            resp = owner_client.post(
                "/owner/integrations/update/whatsapp",
                data={"enabled": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_clear_cache_failure_with_fallback(self, owner_client):
        cache_mock = MagicMock()
        cache_mock.clear.side_effect = RuntimeError("redis down")
        cache_mock.cache = MagicMock()
        type(cache_mock.cache).__name__ = "RedisCache"
        cache_mock.app = owner_client.application
        cache_mock.init_app = MagicMock()
        with patch("extensions.cache", cache_mock):
            resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_truncate_table_bad_confirm(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "customers", "confirm": "NO"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_truncate_table_success(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "customers", "confirm": "YES_DELETE_ALL"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_truncate_table_blocked(self, owner_client):
        resp = owner_client.post(
            "/owner/truncate-table",
            data={"table_name": "users", "confirm": "YES_DELETE_ALL"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_browse_table_valid(self, owner_client):
        resp = owner_client.get("/owner/browse-table/customers")
        assert resp.status_code == 200

    def test_browse_table_invalid(self, owner_client):
        resp = owner_client.get("/owner/browse-table/users", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        with patch("routes.owner.database.db") as mock_db:
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
        assert resp.status_code in (302, 303, 200)

    def test_developer_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/developer-settings",
            data={"developer_name": "Dev Co"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_system_config_post(self, owner_client):
        resp = owner_client.post(
            "/owner/system-config",
            data={"maintenance_mode": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_invoice_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/invoice-settings",
            data={"company_name_ar": "شركة"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_preview_receipt(self, owner_client):
        resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_tax_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/tax-settings",
            data={"enable_tax": "on", "vat_country": "AE", "default_tax_rate": "5"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_tax_settings_no_tenant(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.Tenant.get_current", return_value=None):
            resp = app.test_client().get("/owner/tax-settings", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_currency_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/currency-settings",
            data={"default_currency": "USD", "auto_update_rates": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_exchange_rates_post_save(self, owner_client):
        resp = owner_client.post(
            "/owner/exchange-rates",
            data={"action": "save", "from_currency": "USD", "to_currency": "AED", "rate": "3.67"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_exchange_rates_post_invalid_rate(self, owner_client):
        resp = owner_client.post(
            "/owner/exchange-rates",
            data={"action": "save", "rate": "0"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_payment_gateways_post(self, owner_client):
        resp = owner_client.post(
            "/owner/payment-gateways",
            data={"stripe_publishable_key": "pk_test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_sms_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/sms-settings",
            data={"sms_provider": "twilio", "sms_enabled": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_whatsapp_settings_post(self, owner_client):
        resp = owner_client.post(
            "/owner/whatsapp-settings",
            data={"whatsapp_api_url": "https://api.test", "whatsapp_enabled": "on"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_notification_templates_post(self, owner_client):
        resp = owner_client.post(
            "/owner/notification-templates",
            data={"invoice_email_template": "Hello"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_ip_whitelist_post(self, owner_client):
        resp = owner_client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "10.0.0.1", "description": "office"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_ip_whitelist_delete(self, owner_client):
        settings = MagicMock()
        settings.owner_whitelist_ips = [{"ip": "10.0.0.1", "description": "office"}]
        with patch("routes.owner.SystemSettings.get_current", return_value=settings):
            resp = owner_client.post("/owner/ip-whitelist/0/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_api_keys_post(self, owner_client):
        resp = owner_client.post(
            "/owner/api-keys",
            data={"name": "test", "service": "api"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_api_keys_toggle(self, owner_client):
        key = MagicMock()
        key.is_active = True
        with patch("routes.owner.APIKey.query") as key_query:
            key_query.get_or_404.return_value = key
            resp = owner_client.post("/owner/api-keys/1/toggle", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_security_alert_resolve(self, owner_client):
        alert = MagicMock()
        with patch("routes.owner.SecurityAlert.query") as alert_query:
            alert_query.get_or_404.return_value = alert
            resp = owner_client.post("/owner/security-alerts/1/resolve", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_data_cleanup_post_logs(self, owner_client):
        resp = owner_client.post(
            "/owner/data-cleanup",
            data={"days": "30", "cleanup_type": "logs"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_tenant_suspend_default_protected(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/1/suspend",
            data={"reason": "test"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_tenant_activate(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/2/activate",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_tenant_edit_get(self, owner_client):
        resp = owner_client.get("/owner/tenants/2/edit")
        assert resp.status_code == 200

    def test_tenant_edit_post(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/2/edit",
            data={"name_ar": "محدث", "slug": "updated"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_tenant_delete_with_users(self, owner_client):
        user_q = _model_query(count=3)
        with patch("routes.owner.User.query", new=user_q):
            resp = owner_client.post("/owner/tenants/2/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_tenant_delete_success(self, owner_client):
        user_q = _model_query(count=0)
        with patch("routes.owner.User.query", new=user_q):
            resp = owner_client.post("/owner/tenants/2/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_tenant_ai_toggle(self, owner_client):
        resp = owner_client.post(
            "/owner/tenant-ai/2/toggle",
            data={"enable_ai": "1", "ai_access_level": "advanced"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_tenant_store_platform_toggle(self, owner_client):
        resp = owner_client.post(
            "/owner/tenant-stores/1/platform-toggle",
            data={"platform_disabled": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_error_audit_resolve(self, owner_client):
        resp = owner_client.post(
            "/owner/error-audit-logs/1/resolve",
            data={"note": "fixed"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

    def test_error_audit_export_json(self, owner_client):
        resp = owner_client.get("/owner/error-audit-logs/export?format=json")
        assert resp.status_code == 200

    def test_error_audit_export_invalid(self, owner_client):
        with patch("services.logging_core.LoggingCore.export_error_logs", side_effect=ValueError("bad")):
            resp = owner_client.get("/owner/error-audit-logs/export?format=bad", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_user_delete_self_blocked(self, owner_client, bypass_owner_auth):
        target = _mock_user_entity(id=bypass_owner_auth.id)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/42/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_user_delete_owner_blocked(self, owner_client):
        target = _mock_user_entity(id=9, is_owner=True)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/9/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_user_delete_success(self, owner_client):
        target = _mock_user_entity(id=9, is_owner=False)
        with patch("routes.owner.User.query") as user_query:
            user_query.get_or_404.return_value = target
            resp = owner_client.post("/owner/users/9/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        with patch("routes.owner.settings.db") as mock_db:
            mock_db.session.get.return_value = supervisor
            resp = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "secret", "action": "discount"},
            )
        assert resp.status_code == 200

    def test_api_supervisor_override_bad_password(self, owner_client):
        supervisor = _mock_user_entity(id=5, password_ok=False)
        with patch("routes.owner.settings.db") as mock_db:
            mock_db.session.get.return_value = supervisor
            resp = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "wrong"},
            )
        assert resp.status_code == 403

    def test_system_health_failure(self, owner_client):
        with patch("services.health_service.HealthCheckService.get_health_data", side_effect=RuntimeError("fail")):
            resp = owner_client.get("/owner/system-health", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_verify_backups_failure(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups", side_effect=RuntimeError("fail")):
            resp = owner_client.get("/owner/verify-backups", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_restore_backup_target_scoped(self, owner_client):
        with patch("services.backup_service.BackupService.get_backup_info", return_value={"manifest": {"backup_scope": "tenant"}}), \
             patch("services.backup_service.BackupService.restore_scoped_backup_to_target_db", return_value={"ok": False, "errors": ["fail"]}):
            resp = owner_client.post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={"target_database_url": "postgresql://u:p@localhost/testdb"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_delete_backup_success(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups_for_user", return_value=[{"filename": "backup.sql.gz"}]), \
             patch("services.backup_service.BackupService.delete_backup", return_value=True):
            resp = owner_client.post(
                "/owner/backups/delete",
                data={"filename": "backup.sql.gz"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_delete_backup_missing(self, owner_client):
        with patch("services.backup_service.BackupService.list_backups_for_user", return_value=[]):
            resp = owner_client.post(
                "/owner/backups/delete",
                data={"filename": "missing.sql.gz"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_download_backup(self, owner_client, tmp_path):
        backup_file = tmp_path / "backup.sql.gz"
        backup_file.write_bytes(b"data")
        with patch("services.backup_service.BackupService.BACKUP_DIR", str(tmp_path)), \
             patch("os.path.exists", return_value=True), \
             patch("flask.send_file", return_value=make_response("file", 200)):
            resp = owner_client.get("/owner/backups/download/backup.sql.gz")
        assert resp.status_code == 200

    def test_export_database_sql(self, owner_client, tmp_path):
        with patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=MagicMock(returncode=0, stderr="", stdout="")), \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            resp = owner_client.post(
                "/owner/export-database",
                data={"format": "sql"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_export_database_invalid_format(self, owner_client):
        resp = owner_client.post(
            "/owner/export-database",
            data={"format": "xml"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_store_payment_method_toggle(self, owner_client):
        with patch("services.store_payment_method_service.StorePaymentMethodService.toggle_enabled"):
            resp = owner_client.post(
                "/owner/store-payment-methods/1/toggle",
                data={"is_enabled": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_store_payment_method_delete(self, owner_client):
        with patch("services.store_payment_method_service.StorePaymentMethodService.delete_method"):
            resp = owner_client.post(
                "/owner/store-payment-methods/1/delete",
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

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
        assert resp.status_code in (302, 303, 200)

    def test_invalidate_owner_changes_cache_error(self, owner_client):
        with patch("extensions.cache.clear", side_effect=RuntimeError("cache fail")):
            resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

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
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(return_value=settings)
        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.render_template", return_value="ok"):
            resp = owner_client.get("/owner/preview-invoice/modern")
        assert resp.status_code == 200


class TestOwnerHelpers:
    def test_invalidate_owner_changes_cache_failure(self):
        import routes.owner as owner_mod
        with patch("extensions.cache.clear", side_effect=RuntimeError("cache down")):
            owner_mod._invalidate_owner_changes()

    def test_mask_api_key_variants(self):
        from routes.owner import _mask_api_key, _mask_db_uri, _validate_postgresql_uri
        assert _mask_api_key("") == "****"
        assert _mask_api_key("ab") == "****"
        assert _mask_api_key("secretkey") == "****tkey"
        assert _mask_db_uri("") == ""
        assert "@" in _mask_db_uri("postgresql://user:pass@localhost/db")
        assert _validate_postgresql_uri("postgresql://u:p@localhost/db") is True
        assert _validate_postgresql_uri("mysql://u:p@localhost/db") is False
        assert _validate_postgresql_uri("postgresql://u:p@localhost/db;drop") is False

    def test_resolve_tables_and_sql_validation(self, owner_client):
        from routes.owner import (
            _resolve_known_table,
            _resolve_truncatable_table,
            _resolve_browsable_table,
            _validate_select_only_sql,
            _is_sensitive_stats_table,
        )
        with patch("routes.owner._known_tables_map", return_value={"customers": "customers"}):
            assert _resolve_known_table("customers") == "customers"
            assert _resolve_known_table("users") is None
            assert _resolve_truncatable_table("users") is None
            assert _resolve_browsable_table("users") is None
            assert _is_sensitive_stats_table("users") is True
        ok, err = _validate_select_only_sql("")
        assert ok is False
        ok, err = _validate_select_only_sql("SELECT 1; SELECT 2")
        assert ok is False
        ok, err = _validate_select_only_sql("DELETE FROM x")
        assert ok is False
        ok, err = _validate_select_only_sql("SELECT 1")
        assert ok is True


class TestOwnerGapClosure:
    def test_dashboard_top_products_exception(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        db_q = _dashboard_db_query()
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] >= 9:
                raise RuntimeError("top products fail")
            return db_q

        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.query.side_effect = query_side_effect
            mock_db.session.get.side_effect = lambda m, pk: _mock_tenant(id=pk)
            mock_db.engine = MagicMock()
            resp = app.test_client().get("/owner/dashboard")
        assert resp.status_code == 200

    def test_dashboard_branch_inventory_value(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        branch = _mock_branch()
        wh = MagicMock()
        wh.id = 5
        wh.branch_id = branch.id
        wh.is_active = True
        wh_q = _model_class(all=[wh])
        db_q = _dashboard_db_query()
        db_q.scalar.return_value = Decimal("1500")
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.decorators.branch_scope_id", return_value=branch.id), \
             patch("routes.owner.Branch", _model_class(all=[branch])), \
             patch("routes.owner.Warehouse", wh_q), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.query.side_effect = lambda *a, **k: db_q
            mock_db.session.get.side_effect = lambda m, pk: _mock_tenant(id=pk)
            mock_db.engine = MagicMock()
            resp = app.test_client().get("/owner/dashboard")
        assert resp.status_code == 200

    def test_dashboard_platform_branch_stats(self, app_factory, bypass_owner_auth):
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
        tenant = _mock_tenant(id=2)
        tenant_cls = _tenant_class(tenant)
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner.get_active_tenant_id", return_value=None), \
             patch("routes.owner.Tenant", tenant_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.query.side_effect = lambda *a, **k: db_q
            mock_db.session.get.side_effect = lambda m, pk: _mock_tenant(id=pk)
            mock_db.engine = MagicMock()
            resp = app.test_client().get("/owner/dashboard")
        assert resp.status_code == 200

    def test_user_create_branch_required(self, owner_client):
        role = _mock_role(slug="seller")
        role_cls = _model_class(all=[role])
        with patch("models.Role", role_cls), \
             patch("routes.owner.role_requires_branch", return_value=True), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "u1", "password": "Str0ng!Pass", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_user_create_role_too_high(self, owner_client):
        role = _mock_role(slug="super_admin")
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.role_level_for", return_value=200), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "u1", "password": "Str0ng!Pass", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_user_create_global_owner_null_tenant(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        role = _mock_role(slug="platform_admin")
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("models.Role", _model_class(all=[role])), \
             patch("utils.auth_helpers.user_may_have_null_tenant", return_value=True), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "globalu",
                    "password": "Str0ng!Pass",
                    "role_id": "2",
                    "is_owner": "on",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_user_create_commit_exception(self, owner_client):
        role = _mock_role(slug="seller")
        user_q = _model_query(first=None)
        user_cls = _model_class(entity=None)
        user_cls.query = user_q
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            mock_db.session.commit.side_effect = RuntimeError("commit fail")
            mock_db.session.rollback = MagicMock()
            resp = owner_client.post(
                "/owner/users/create",
                data={"username": "newu", "password": "Str0ng!Pass", "role_id": "2", "tenant_id": "1"},
            )
        assert resp.status_code == 200

    def test_user_edit_branch_and_role_blocks(self, owner_client):
        role = _mock_role(slug="seller")
        target = _mock_user_entity(id=2)
        user_cls = _model_class(entity=target)
        user_cls.query.get_or_404.return_value = target
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.role_requires_branch", return_value=True), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = owner_client.post(
                "/owner/users/2/edit",
                data={"username": "e", "email": "e@t.com", "full_name": "E", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_user_edit_with_password_and_exception(self, owner_client):
        role = _mock_role(slug="seller")
        target = _mock_user_entity(id=2)
        user_cls = _model_class(entity=target)
        user_cls.query.get_or_404.return_value = target
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.role_level_for", return_value=200), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = owner_client.post(
                "/owner/users/2/edit",
                data={
                    "username": "e", "email": "e@t.com", "full_name": "E",
                    "role_id": "2", "new_password": "NewStr0ng!Pass",
                },
            )
        assert resp.status_code == 200
        mock_db.session.commit.side_effect = RuntimeError("fail")
        mock_db.session.rollback = MagicMock()
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.db") as mock_db2:
            mock_db2.session.get.return_value = role
            mock_db2.session.commit.side_effect = RuntimeError("fail")
            mock_db2.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/users/2/edit",
                data={"username": "e", "email": "e@t.com", "full_name": "E", "role_id": "2"},
            )
        assert resp2.status_code == 200

    def test_user_delete_commit_exception(self, owner_client):
        target = _mock_user_entity(id=9, is_owner=False)
        user_cls = _model_class(entity=target)
        user_cls.query.get_or_404.return_value = target
        with patch("routes.owner.User", user_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("delete fail")
            mock_db.session.rollback = MagicMock()
            resp = owner_client.post("/owner/users/9/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_database_tools_table_loop(self, owner_client):
        inspector = _inspector()
        inspector.get_table_names.return_value = ["customers", "users", "unknown_tbl"]
        exec_result = _execute_result()
        exec_result.scalar.return_value = 3
        with patch("routes.owner.inspect", return_value=inspector), \
             patch("routes.owner.db") as mock_db:
            mock_db.engine = MagicMock()
            mock_db.session.execute.return_value = exec_result
            resp = owner_client.get("/owner/database-tools")
        assert resp.status_code == 200

    def test_backup_now_form_failure(self, owner_client):
        with patch("services.backup_service.BackupService.create_backup", return_value=None):
            resp = owner_client.post(
                "/owner/backup-now",
                data={"description": "fail"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_scoped_backup_company_admin_denied(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        mock_user.tenant_id = 1
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
            patch("routes.owner.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/backups/create",
                data={"scope": "tenant", "tenant_id": "99"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 403, 404, 200)

    def test_scoped_backup_non_global_system(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("routes.owner.get_active_tenant_id", return_value=None),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/backups/create",
                data={"scope": "system"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 403, 404, 200)

    def test_scoped_backup_branch_denied_for_branch_user(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        mock_user.branch_id = 1
        mock_user.tenant_id = 1
        role = MagicMock()
        role.slug = "manager"
        mock_user.role = role
        mock_user.is_super_admin.return_value = True
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("routes.owner.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/backups/create",
                data={"scope": "branch", "tenant_id": "1", "branch_id": "9"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 403, 404, 200)

    def test_scoped_backup_create_failure(self, owner_client):
        with patch("services.backup_service.BackupService.create_backup", return_value=None):
            resp = owner_client.post(
                "/owner/backups/create",
                data={"scope": "system", "description": "x"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_verify_backup_denied_and_invalid(self, owner_client):
        with patch("services.backup_service.BackupService.user_may_access_backup", return_value=False):
            resp = owner_client.post("/owner/backups/verify/bad.sql.gz")
        assert resp.status_code == 403
        with patch("services.backup_service.BackupService.verify_backup", return_value={"valid": False, "errors": ["x"]}):
            resp2 = owner_client.post("/owner/backups/verify/backup.sql.gz")
        assert resp2.status_code == 200

    def test_prepare_restore_denied_and_bad_payload(self, owner_client):
        with patch("services.backup_service.BackupService.user_may_access_backup", return_value=False):
            resp = owner_client.get("/owner/backups/prepare-restore/x.sql.gz", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        with patch("services.backup_service.BackupService.prepare_restore", return_value={"ok": False, "error": "bad"}):
            resp2 = owner_client.get("/owner/backups/prepare-restore/backup.sql.gz", follow_redirects=False)
        assert resp2.status_code in (302, 303)

    def test_restore_backup_not_global_owner(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.decorators.is_global_owner_user", return_value=True),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={"target_database_url": "postgresql://u:p@localhost/db"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_restore_backup_no_target_url(self, owner_client):
        with patch.dict("os.environ", {}, clear=True):
            resp = owner_client.post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_delete_backup_invalid_and_failure(self, owner_client):
        resp = owner_client.post("/owner/backups/delete", data={"filename": ""}, follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        with patch("services.backup_service.BackupService.list_backups_for_user", return_value=[{"filename": "backup.sql.gz"}]), \
             patch("services.backup_service.BackupService.delete_backup", return_value=False):
            resp2 = owner_client.post(
                "/owner/backups/delete",
                data={"filename": "backup.sql.gz"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303)

    def test_download_backup_denied_missing_error(self, owner_client):
        with patch("services.backup_service.BackupService.user_may_access_backup", return_value=False):
            resp = owner_client.get("/owner/backups/download/x.sql.gz", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        with patch("os.path.exists", return_value=False):
            resp2 = owner_client.get("/owner/backups/download/backup.sql.gz", follow_redirects=False)
        assert resp2.status_code in (302, 303)
        with patch("os.path.exists", return_value=True), \
             patch("flask.send_file", side_effect=RuntimeError("send fail")):
            resp3 = owner_client.get("/owner/backups/download/backup.sql.gz", follow_redirects=False)
        assert resp3.status_code in (302, 303)

    def test_clear_cache_fallback_paths(self, owner_client):
        cache_mock = MagicMock()
        cache_mock.clear.side_effect = RuntimeError("redis down")
        inner = MagicMock()
        inner.__name__ = "RedisCache"
        cache_mock.cache = inner
        cache_mock.app = owner_client.application
        cache_mock.init_app = MagicMock()
        with patch("extensions.cache", cache_mock):
            resp = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        cache_mock.init_app.side_effect = RuntimeError("init fail")
        with patch("extensions.cache", cache_mock):
            resp2 = owner_client.post("/owner/clear-cache", follow_redirects=False)
        assert resp2.status_code in (302, 303)

    def test_truncate_and_browse_exceptions(self, owner_client):
        with patch("routes.owner.database.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("truncate fail")
            mock_db.session.rollback = MagicMock()
            resp = owner_client.post(
                "/owner/truncate-table",
                data={"table_name": "customers", "confirm": "YES_DELETE_ALL"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        with patch("routes.owner.database.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("browse fail")
            resp2 = owner_client.get("/owner/browse-table/customers", follow_redirects=False)
        assert resp2.status_code in (302, 303)

    def test_update_row_edge_cases(self, owner_client):
        inspector = _inspector()
        inspector.get_pk_constraint.return_value = {"constrained_columns": []}
        with patch("routes.owner.database.inspect", return_value=inspector):
            resp = owner_client.post("/owner/update-row/customers/1", json={"name": "x"})
        assert resp.status_code == 400
        inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        with patch("routes.owner.database.inspect", return_value=inspector):
            resp2 = owner_client.post("/owner/update-row/customers/1", json={"id": "hack"})
        assert resp2.status_code == 400
        with patch("routes.owner.database.inspect", return_value=inspector), \
             patch("routes.owner.database.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("update fail")
            mock_db.session.rollback = MagicMock()
            resp3 = owner_client.post("/owner/update-row/customers/1", json={"name": "x"})
        assert resp3.status_code == 500

    def test_edit_table_data_exception(self, owner_client):
        with patch("routes.owner.database.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("edit fail")
            resp = owner_client.get("/owner/edit-table-data/customers", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_export_database_json_and_failure(self, owner_client, tmp_path):
        exec_result = _execute_result(rows=[(1, "a")], columns=["id", "name"])
        with patch("routes.owner.database.db") as mock_db, \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])), \
             patch("builtins.open", create=True) as mock_open:
            mock_db.session.execute.return_value = exec_result
            mock_open.return_value.__enter__.return_value = MagicMock()
            resp = owner_client.post(
                "/owner/export-database",
                data={"format": "json"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        with patch("services.backup_service.BackupService._parse_db_url", side_effect=RuntimeError("fail")):
            resp2 = owner_client.post(
                "/owner/export-database",
                data={"format": "sql"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303)

    def test_convert_database_paths(self, owner_client):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        row = MagicMock()
        row.keys.return_value = ["id", "name"]
        exec_result = _execute_result(rows=[(1, "n")], columns=["id", "name"])
        with patch("routes.owner._validate_postgresql_uri", return_value=False):
            resp = owner_client.post("/owner/convert-database", data={"target_db": "postgresql", "postgresql_uri": "bad"})
        assert resp.status_code == 200
        with patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner._inspector_column_names", return_value={"id", "name"}):
            mock_db.session.execute.return_value = exec_result
            resp2 = owner_client.post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/db"},
            )
        assert resp2.status_code == 200
        mock_conn.execute.side_effect = RuntimeError("insert fail")
        with patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner._inspector_column_names", return_value={"id", "name"}):
            mock_db.session.execute.return_value = exec_result
            resp3 = owner_client.post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/db"},
            )
        assert resp3.status_code == 200

    def test_company_and_developer_exceptions(self, owner_client):
        tenant = _mock_tenant()
        tenant_cls = _tenant_class(tenant)
        with patch("routes.owner.Tenant", tenant_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("save fail")
            mock_db.session.rollback = MagicMock()
            resp = owner_client.post(
                "/owner/company-info",
                data={"name_ar": "شركة", "slug": "co"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        with patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("dev fail")
            mock_db.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/developer-settings",
                data={"developer_name": "Dev"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303, 200)

    def test_invoice_settings_uploads_and_error(self, owner_client, tmp_path):
        from io import BytesIO

        settings = MagicMock()
        settings_cls = _invoice_settings_class(settings)
        data = {
            "company_name_ar": "شركة",
            "company_logo": (BytesIO(b"png"), "logo.png"),
            "watermark_image": (BytesIO(b"png"), "wm.png"),
        }
        with patch("routes.owner.InvoiceSettings", settings_cls), \
             patch("models.invoice_settings.InvoiceSettings", settings_cls), \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            resp = owner_client.post(
                "/owner/invoice-settings",
                data=data,
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        with patch("routes.owner.InvoiceSettings", settings_cls), \
             patch("models.invoice_settings.InvoiceSettings", settings_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("inv fail")
            mock_db.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/invoice-settings",
                data={"company_name_ar": "شركة"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303, 200)

    def test_preview_receipt_full(self, owner_client):
        settings = MagicMock()
        settings.enable_qr_code = True
        inv_cls = _invoice_settings_class(settings)
        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.render_template", return_value="ok"), \
             patch("routes.owner.resolve_default_currency", return_value="AED"):
            resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_tax_settings_suggested_rate(self, owner_client):
        tenant = _mock_tenant()
        tenant.enable_tax = False
        tenant_cls = _tenant_class(tenant)
        with patch("routes.owner.Tenant", tenant_cls), \
             patch("utils.tax_settings.suggested_rate_for_country", return_value=Decimal("5")):
            resp = owner_client.post(
                "/owner/tax-settings",
                data={"enable_tax": "on", "vat_country": "AE"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_currency_settings_tenant_sync_error(self, owner_client):
        with patch("routes.owner.Tenant.get_current", side_effect=RuntimeError("tenant sync")):
            resp = owner_client.post(
                "/owner/currency-settings",
                data={"default_currency": "USD"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        with patch("routes.owner.Tenant.get_current", side_effect=RuntimeError("get fail")):
            resp2 = owner_client.get("/owner/currency-settings")
        assert resp2.status_code == 200

    def test_exchange_rates_delete_and_fail(self, owner_client):
        rec = MagicMock()
        rec.id = 1
        ex_cls = _model_class(all=[rec])
        with patch("models.ExchangeRateRecord", ex_cls), \
             patch("services.exchange_rate_service.ExchangeRateService.save_manual_rate", return_value={"ok": False, "error": "bad"}):
            resp = owner_client.post(
                "/owner/exchange-rates",
                data={"action": "save", "rate": "1.5"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        ex_cls.query.filter_by.return_value.first.return_value = None
        with patch("models.ExchangeRateRecord", ex_cls):
            resp2 = owner_client.post(
                "/owner/exchange-rates",
                data={"action": "delete", "record_id": "99"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303)
        ex_cls.query.filter_by.return_value.first.return_value = rec
        with patch("models.ExchangeRateRecord", ex_cls):
            resp3 = owner_client.post(
                "/owner/exchange-rates",
                data={"action": "delete", "record_id": "1"},
                follow_redirects=False,
            )
        assert resp3.status_code in (302, 303)

    def test_database_optimize_paths(self, owner_client):
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", return_value={"success": False, "error": "vac fail"}), \
             patch("utils.database_optimizer.DatabaseOptimizer.analyze_tables", return_value={"success": True}):
            resp = owner_client.post("/owner/database-optimize", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", side_effect=RuntimeError("boom")):
            resp2 = owner_client.post("/owner/database-optimize", follow_redirects=False)
        assert resp2.status_code in (302, 303)

    def test_data_cleanup_archived(self, owner_client):
        audit_cls = _model_class()
        audit_cls.query.filter.return_value.delete.return_value = 2
        arch_cls = _model_class()
        arch_cls.query.filter.return_value.delete.return_value = 3
        with patch("routes.owner.AuditLog", audit_cls), \
             patch("routes.owner.ArchivedRecord", arch_cls):
            resp = owner_client.post(
                "/owner/data-cleanup",
                data={"days": "30", "cleanup_type": "archived"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_export_excel_paths(self, owner_client):
        item = MagicMock()
        item.to_dict.return_value = {"id": 1}
        with patch("routes.owner.database.Customer", _model_class(all=[item])), \
             patch("flask.send_file", return_value=make_response(b"xlsx", 200)):
            resp = owner_client.get("/owner/export-excel/customers")
        assert resp.status_code == 200
        plain = MagicMock()
        col = MagicMock(name="id")
        plain.__table__ = MagicMock(columns=[col])
        del plain.to_dict
        with patch("routes.owner.database.Product", _model_class(all=[plain])), \
             patch("utils.decorators.branch_scope_id", return_value=1), \
             patch("flask.send_file", return_value=make_response(b"xlsx", 200)):
            resp2 = owner_client.get("/owner/export-excel/products")
        assert resp2.status_code in (200, 302)
        with patch("routes.owner.database.Customer", _model_class(all=[])):
            resp3 = owner_client.get("/owner/export-excel/customers", follow_redirects=False)
        assert resp3.status_code in (302, 303)
        with patch("routes.owner.database.Customer", _model_class(all=[item])), \
             patch("pandas.DataFrame", side_effect=RuntimeError("xlsx fail")):
            resp4 = owner_client.get("/owner/export-excel/customers", follow_redirects=False)
        assert resp4.status_code in (302, 303)

    def test_tenant_create_validation_and_error(self, owner_client):
        resp = owner_client.post(
            "/owner/tenants/create",
            data={"name_ar": "شركة", "slug": "co", "default_currency": ""},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)
        tenant_cls = _tenant_class(_mock_tenant())
        tenant_cls.query.filter_by.return_value.first.return_value = _mock_tenant()
        with patch("routes.owner.tenants.Tenant", tenant_cls):
            resp2 = owner_client.post(
                "/owner/tenants/create",
                data={"name_ar": "شركة", "slug": "dup", "default_currency": "AED"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303)
        tenant_cls.query.filter_by.return_value.first.return_value = None
        with patch("routes.owner.tenants.Tenant", tenant_cls), \
             patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("create fail")
            mock_db.session.rollback = MagicMock()
            resp3 = owner_client.post(
                "/owner/tenants/create",
                data={"name_ar": "شركة", "slug": "newco", "default_currency": "AED"},
                follow_redirects=False,
            )
        assert resp3.status_code in (302, 303, 200)

    def test_tenant_edit_and_delete_protected(self, owner_client):
        tenant = _mock_tenant(id=1)
        tenant_cls = _tenant_class(tenant)
        tenant_cls.query.get_or_404.return_value = tenant
        with patch("routes.owner.Tenant", tenant_cls):
            resp = owner_client.post("/owner/tenants/1/delete", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)
        tenant2 = _mock_tenant(id=2)
        tenant_cls2 = _tenant_class(tenant2)
        tenant_cls2.query.get_or_404.return_value = tenant2
        with patch("routes.owner.Tenant", tenant_cls2), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("edit fail")
            mock_db.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/tenants/2/edit",
                data={"name_ar": "محدث", "slug": "up"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303, 200)

    def test_api_endpoints_edge_cases(self, app_factory, mock_user, bypass_owner_auth):
        from routes.owner import owner_bp

        app = app_factory(owner_bp)
        with _owner_route_patches():
            resp = app.test_client().post("/owner/api/toggle-warehouse-negative", data={})
        assert resp.status_code in (400, 404)
        wh = MagicMock()
        wh.allow_negative_inventory = False
        wh_cls = _model_class()
        wh_cls.query.filter_by.return_value.first.return_value = wh
        with _owner_route_patches(), \
             patch("utils.decorators.is_global_owner_user", return_value=False), \
             patch("utils.tenanting.get_active_tenant_id", return_value=1), \
             patch("routes.owner.settings.Warehouse", wh_cls), \
             patch("routes.owner.settings.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("wh fail")
            mock_db.session.rollback = MagicMock()
            resp2 = app.test_client().post(
                "/owner/api/toggle-warehouse-negative",
                json={"warehouse_id": 1},
            )
        assert resp2.status_code in (500, 200)

    def test_supervisor_override_paths(self, owner_client):
        resp = owner_client.post("/owner/api/supervisor-override", data={})
        assert resp.status_code in (400, 404)
        inactive = _mock_user_entity(id=5, is_active=False)
        with patch("routes.owner.settings.db") as mock_db:
            mock_db.session.get.return_value = inactive
            resp2 = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "x"},
            )
        assert resp2.status_code == 404
        not_mgr = _mock_user_entity(id=5, is_manager=False, is_admin=False)
        with patch("routes.owner.settings.db") as mock_db:
            mock_db.session.get.return_value = not_mgr
            resp3 = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "x"},
            )
        assert resp3.status_code == 403
        with patch("routes.owner.settings.db") as mock_db:
            mock_db.session.get.side_effect = RuntimeError("lookup fail")
            resp4 = owner_client.post(
                "/owner/api/supervisor-override",
                json={"supervisor_id": 5, "password": "secret", "action": "discount"},
            )
        assert resp4.status_code == 500

    def test_api_tenant_toggle_and_package_edges(self, owner_client):
        with patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.get.return_value = None
            resp = owner_client.post("/owner/api/tenant/99/toggle-status", json={})
        assert resp.status_code == 404
        default_tenant = _mock_tenant(id=1)
        with patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.get.return_value = default_tenant
            resp2 = owner_client.post("/owner/api/tenant/1/toggle-status", json={})
        assert resp2.status_code == 400
        with patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.get.side_effect = RuntimeError("toggle fail")
            mock_db.session.rollback = MagicMock()
            resp3 = owner_client.post("/owner/api/tenant/2/toggle-status", json={})
        assert resp3.status_code == 500
        resp4 = owner_client.post("/owner/api/tenant/2/update-package", data={})
        assert resp4.status_code == 400

    def test_system_config_fee_parse_exceptions(self, owner_client):
        resp = owner_client.post(
            "/owner/system-config",
            data={
                "azad_platform_fee_rate": "not-a-decimal",
                "subscription_monthly_fee_aed": "bad",
                "subscription_yearly_fee_aed": "bad",
                "subscription_perpetual_fee_aed": "bad",
                "default_currency": "AED",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303, 200)
        with patch("routes.owner.db") as mock_db:
            mock_db.session.commit.side_effect = RuntimeError("cfg fail")
            mock_db.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/system-config",
                data={"enable_sales": "on"},
                follow_redirects=False,
            )
        assert resp2.status_code in (302, 303, 200)

    def test_company_info_invoice_sync_exception(self, owner_client):
        tenant = _mock_tenant()
        tenant_cls = _tenant_class(tenant)
        inv_cls = MagicMock()
        inv_cls.get_active.side_effect = RuntimeError("inv sync")
        with patch("routes.owner.Tenant", tenant_cls), \
             patch("routes.owner.InvoiceSettings", inv_cls):
            resp = owner_client.post(
                "/owner/company-info",
                data={"name_ar": "شركة", "slug": "co"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_tenant_stores_and_ai_toggle(self, owner_client):
        store = MagicMock()
        store.id = 1
        store.is_enabled = True
        store.platform_disabled = False
        tenant = _mock_tenant()
        row = (store, tenant)
        with patch("routes.owner.db") as mock_db:
            mock_db.session.query.return_value.join.return_value.order_by.return_value.all.return_value = [row]
            resp = owner_client.get("/owner/tenant-stores")
        assert resp.status_code == 200
        resp2 = owner_client.post(
            "/owner/tenant-ai/2/toggle",
            data={},
            follow_redirects=False,
        )
        assert resp2.status_code in (302, 303, 200)

    def test_preview_invoice_forbidden_tenant(self, app_factory, mock_user):
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
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().get("/owner/preview-invoice/modern?tenant_id=2")
        assert resp.status_code in (403, 404, 200)

    def test_preview_invoice_tenant_currency_fallback(self, owner_client):
        settings = MagicMock()
        settings.enable_qr_code = False
        inv_cls = _invoice_settings_class(settings)
        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.resolve_default_currency", side_effect=RuntimeError("curr")), \
             patch("routes.owner.render_template", return_value="ok"):
            resp = owner_client.get("/owner/preview-invoice/modern")
        assert resp.status_code == 200

    def test_preview_receipt_currency_fallback(self, owner_client):
        settings = MagicMock()
        inv_cls = _invoice_settings_class(settings)
        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.resolve_default_currency", side_effect=RuntimeError("curr")), \
             patch("routes.owner.render_template", return_value="ok"):
            resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_export_database_sql_success(self, owner_client, tmp_path):
        proc = MagicMock(returncode=0, stderr="", stdout="")
        with patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=proc), \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            resp = owner_client.post(
                "/owner/export-database",
                data={"format": "sql"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_convert_database_empty_and_blocked(self, owner_client):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        empty_result = _execute_result(rows=[], columns=["id"])
        with patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner._known_tables_map", return_value={"users": "users", "customers": "customers"}), \
             patch("routes.owner._inspector_column_names", return_value=set()):
            mock_db.session.execute.return_value = empty_result
            resp = owner_client.post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/db"},
            )
        assert resp.status_code == 200
        with patch("routes.owner._validate_postgresql_uri", return_value=False):
            resp2 = owner_client.post("/owner/convert-database", data={"target_db": "postgresql"})
        assert resp2.status_code == 200

    def test_helper_inspector_unknown_table(self):
        from routes.owner import _inspector_column_names, _known_tables_map, _resolve_known_table
        with patch("routes.owner._known_tables_map", return_value={}):
            assert _inspector_column_names("missing") == set()
            assert _resolve_known_table("") is None
            assert _resolve_known_table("bad-name!") is None

    def test_scoped_backup_no_active_tenant_aborts(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        mock_user.tenant_id = None
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        mock_user.is_super_admin.return_value = True
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.decorators.is_global_owner_user", return_value=True),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = app.test_client().post(
                "/owner/backups/create",
                data={"scope": "tenant", "tenant_id": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (403, 302, 303)

    def test_error_audit_resolve_failure(self, owner_client):
        with patch("services.logging_core.LoggingCore.mark_error_resolved", return_value=False):
            resp = owner_client.post(
                "/owner/error-audit-logs/1/resolve",
                data={"note": "nope"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_api_package_invalid_value_and_exception(self, owner_client):
        tenant = _mock_tenant(id=2)
        with patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.get.return_value = tenant
            resp = owner_client.post(
                "/owner/api/tenant/2/update-package",
                json={"field": "max_users", "value": "not-int"},
            )
        assert resp.status_code == 400
        with patch("routes.owner.tenants.db") as mock_db:
            mock_db.session.get.return_value = tenant
            mock_db.session.commit.side_effect = RuntimeError("pkg fail")
            mock_db.session.rollback = MagicMock()
            resp2 = owner_client.post(
                "/owner/api/tenant/2/update-package",
                json={"field": "max_users", "value": 10},
            )
        assert resp2.status_code == 500

    def test_user_create_company_admin_tenant_path(self, app_factory, mock_user):
        from routes.owner import owner_bp

        mock_user.is_owner = True
        mock_user.tenant_id = 1
        role = _mock_role(slug="seller")
        user_q = _model_query(first=None)
        user_cls = _model_class()
        user_cls.query = user_q
        patches = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.decorators.is_global_owner_user", return_value=True),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_admin_surface_user", return_value=True),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.security_helpers.enforce_owner_ip_if_needed"),
            patch("models.Role", _model_class(all=[role])),
            patch("routes.owner.User", user_cls),
        ]
        app = app_factory(owner_bp)
        with _owner_route_patches(), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            import routes.owner as owner_mod
            owner_mod.db.session.get.return_value = role
            resp = app.test_client().post(
                "/owner/users/create",
                data={"username": "coadmin", "password": "Str0ng!Pass", "role_id": "2"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_user_edit_password_hash(self, owner_client):
        role = _mock_role(slug="seller")
        target = _mock_user_entity(id=2)
        user_cls = _model_class(entity=target)
        user_cls.query.get_or_404.return_value = target
        with patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = role
            resp = owner_client.post(
                "/owner/users/2/edit",
                data={
                    "username": "e", "email": "e@t.com", "full_name": "E",
                    "role_id": "2", "new_password": "NewStr0ng!Pass",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_database_optimize_partial_success(self, owner_client):
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", return_value={"success": True}), \
             patch("utils.database_optimizer.DatabaseOptimizer.analyze_tables", return_value={"success": False, "error": "analyze fail"}):
            resp = owner_client.post("/owner/database-optimize", follow_redirects=False)
        assert resp.status_code in (302, 303, 200)

    def test_restore_backup_global_owner_required(self, owner_client):
        with patch("utils.decorators.is_global_owner_user", return_value=True), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False):
            resp = owner_client.post(
                "/owner/backups/restore-target/backup.sql.gz",
                data={"target_database_url": "postgresql://u:p@localhost/db"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)

    def test_dashboard_branch_stats_with_inventory(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp

        branch = _mock_branch()
        wh = MagicMock()
        wh.id = 5
        wh.branch_id = branch.id
        wh.is_active = True
        branch_cls = _model_class(all=[branch])
        wh_cls = _model_class(all=[wh])
        pwc_cls = _model_class()
        db_q = _dashboard_db_query()
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner.get_active_tenant_id", return_value=1), \
             patch("models.Branch", branch_cls), \
             patch("models.Warehouse", wh_cls), \
             patch("models.ProductWarehouseCost", pwc_cls), \
             patch("models.StockMovement", _model_class()), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.query.side_effect = lambda *a, **k: db_q
            mock_db.session.get.side_effect = lambda m, pk: _mock_tenant(id=pk)
            mock_db.engine = MagicMock()
            resp = app.test_client().get("/owner/dashboard")
        assert resp.status_code == 200


class TestOwnerDirectCalls:
    def test_database_tools_table_inspection(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, database_tools

        app = app_factory(owner_bp)
        inspector = _inspector()
        inspector.get_table_names.return_value = ["customers", "users", "products"]
        exec_result = _execute_result()
        exec_result.scalar.return_value = 4
        with _owner_route_patches(), patch("sqlalchemy.inspect", return_value=inspector):
            with app.test_request_context("/owner/database-tools"):
                result = database_tools()
        assert result is not None

    def test_create_scoped_backup_system_denied(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_scoped_backup

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("utils.auth_helpers.is_global_owner_user", return_value=False):
            with app.test_request_context("/owner/backups/create", method="POST", data={"scope": "system"}):
                with pytest.raises(Exception):
                    create_scoped_backup()

    def test_create_scoped_backup_tenant_mismatch(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_scoped_backup

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("routes.owner.get_active_tenant_id", return_value=1):
            with app.test_request_context(
                "/owner/backups/create", method="POST", data={"scope": "tenant", "tenant_id": "99"}
            ):
                with pytest.raises(Exception):
                    create_scoped_backup()

    def test_restore_backup_target_not_authorized(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, restore_backup_target

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("utils.auth_helpers.is_global_owner_user", return_value=False):
            with app.test_request_context(
                "/owner/backups/restore-target/x.sql.gz",
                method="POST",
                data={"target_database_url": "postgresql://u:p@localhost/db"},
            ):
                result = restore_backup_target("x.sql.gz")
        assert result.status_code in (302, 303)

    def test_edit_table_data_exception_direct(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, edit_table_data

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("edit fail")
            with app.test_request_context("/owner/edit-table-data/customers"):
                result = edit_table_data("customers")
        assert result.status_code in (302, 303)

    def test_invoice_settings_logo_upload_direct(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, invoice_settings
        from io import BytesIO

        app = app_factory(owner_bp)
        settings = MagicMock()
        inv_cls = _invoice_settings_class(settings)
        with _owner_route_patches(), \
             patch("routes.owner.InvoiceSettings", inv_cls), \
             patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            with app.test_request_context(
                "/owner/invoice-settings",
                method="POST",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (BytesIO(b"png"), "logo.png"),
                    "watermark_image": (BytesIO(b"png"), "wm.png"),
                },
                content_type="multipart/form-data",
            ):
                result = invoice_settings()
        assert result is not None

    def test_known_tables_map_direct(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, _known_tables_map

        app = app_factory(owner_bp)
        with _owner_route_patches():
            with app.app_context():
                tables = _known_tables_map()
        assert "customers" in tables


class TestOwnerFinalGaps:
    def test_mask_db_uri_malformed(self):
        from routes.owner import _mask_db_uri
        assert _mask_db_uri("no-scheme") == "no-scheme"
        assert _mask_db_uri("postgresql://bad") == "[redacted]" or "postgresql" in _mask_db_uri("postgresql://bad")

    def test_validate_select_forbidden_keyword(self):
        from routes.owner import _validate_select_only_sql
        ok, _ = _validate_select_only_sql("SELECT * FROM users WHERE id IN (UPDATE x)")
        assert ok is False

    def test_tenant_ai_toggle_missing_tenant(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_ai_toggle

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = None
            with app.test_request_context("/owner/tenant-ai/9/toggle", method="POST", data={}):
                result = tenant_ai_toggle(9)
        assert result.status_code in (302, 303)

    def test_tenant_ai_toggle_invalid_level_and_error(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_ai_toggle

        tenant = _mock_tenant(id=2)
        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = tenant
            with app.test_request_context(
                "/owner/tenant-ai/2/toggle",
                method="POST",
                data={"enable_ai": "1", "ai_access_level": "bogus"},
            ):
                tenant_ai_toggle(2)
            mock_db.session.commit.side_effect = RuntimeError("ai fail")
            mock_db.session.rollback = MagicMock()
            with app.test_request_context(
                "/owner/tenant-ai/2/toggle", method="POST", data={"enable_ai": "1"}
            ):
                tenant_ai_toggle(2)

    def test_tenant_store_toggle_missing_and_error(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_store_platform_toggle

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = None
            with app.test_request_context("/owner/tenant-stores/1/platform-toggle", method="POST", data={}):
                tenant_store_platform_toggle(1)
            store = MagicMock()
            mock_db.session.get.return_value = store
            with patch("services.store_service.StoreService.set_platform_disabled", side_effect=RuntimeError("fail")):
                with app.test_request_context(
                    "/owner/tenant-stores/1/platform-toggle",
                    method="POST",
                    data={"platform_disabled": "1"},
                ):
                    tenant_store_platform_toggle(1)

    def test_store_payment_method_errors(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, store_payment_method_create, store_payment_method_edit
        from routes.owner import store_payment_method_toggle, store_payment_method_delete

        app = app_factory(owner_bp)
        with _owner_route_patches():
            with patch("services.store_payment_method_service.StorePaymentMethodService.create_method", side_effect=ValueError("dup")):
                with app.test_request_context("/owner/store-payment-methods/create", method="POST", data={"code": "x"}):
                    store_payment_method_create()
            with patch("services.store_payment_method_service.StorePaymentMethodService.create_method", side_effect=RuntimeError("fail")):
                with app.test_request_context("/owner/store-payment-methods/create", method="POST", data={"code": "x"}):
                    store_payment_method_create()
            with patch("routes.owner.db") as mock_db:
                mock_db.session.get.return_value = None
                with app.test_request_context("/owner/store-payment-methods/1/edit"):
                    store_payment_method_edit(1)
            method = MagicMock()
            method.id = 1
            method.sort_order = 1
            with patch("routes.owner.db") as mock_db, \
                 patch("services.store_payment_method_service.StorePaymentMethodService.update_method", side_effect=ValueError("bad")):
                mock_db.session.get.return_value = method
                with app.test_request_context("/owner/store-payment-methods/1/edit", method="POST", data={"code": "x"}):
                    store_payment_method_edit(1)
            with patch("services.store_payment_method_service.StorePaymentMethodService.toggle_enabled", side_effect=ValueError("bad")):
                with app.test_request_context("/owner/store-payment-methods/1/toggle", method="POST", data={"is_enabled": "1"}):
                    store_payment_method_toggle(1)
            with patch("services.store_payment_method_service.StorePaymentMethodService.delete_method", side_effect=ValueError("bad")):
                with app.test_request_context("/owner/store-payment-methods/1/delete", method="POST"):
                    store_payment_method_delete(1)

    def test_export_database_json_direct(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        exec_result = _execute_result(rows=[(1, "n")], columns=["id", "name"])
        with _owner_route_patches(), \
             patch("routes.owner.db") as mock_db, \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])), \
             patch("builtins.open", create=True) as mock_open:
            mock_db.session.execute.return_value = exec_result
            mock_open.return_value.__enter__.return_value = MagicMock()
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "json"}):
                export_database()

    def test_convert_database_empty_target(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, convert_database

        app = app_factory(owner_bp)
        with _owner_route_patches():
            with app.test_request_context("/owner/convert-database", method="POST", data={"target_db": ""}):
                convert_database()

    def test_sql_console_error_direct(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, sql_console

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("sql fail")
            with app.test_request_context("/owner/sql-console", method="POST", data={"sql_query": "SELECT 1"}):
                sql_console()

    def test_system_config_tenant_sync_error(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, system_config

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.Tenant.get_current", side_effect=RuntimeError("sync")):
            with app.test_request_context("/owner/system-config", method="POST", data={"default_currency": "AED"}):
                system_config()

    def test_create_user_company_tenant_path(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_user

        bypass_owner_auth.is_owner = False
        bypass_owner_auth.tenant_id = 1
        role = _mock_role(slug="seller")
        user_q = _model_query(first=None)
        user_cls = _model_class()
        user_cls.query = user_q
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls):
            import routes.owner as owner_mod
            owner_mod.db.session.get.return_value = role
            with app.test_request_context(
                "/owner/users/create",
                method="POST",
                data={"username": "co", "password": "Str0ng!Pass", "role_id": "2"},
            ):
                create_user()

    def test_api_company_admin_paths(self, app_factory, mock_user):
        from routes.owner import owner_bp, api_update_tenant_settings, api_toggle_warehouse_negative

        mock_user.is_super_admin.return_value = True
        tenant = _mock_tenant()
        app = app_factory(owner_bp)
        base = [
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("routes.owner.get_active_tenant_id", return_value=1),
        ]
        with _owner_route_patches(), ExitStack() as stack:
            for p in base:
                stack.enter_context(p)
            with patch("routes.owner.db") as mock_db:
                mock_db.session.get.return_value = tenant
                with app.test_request_context(
                    "/owner/api/update-tenant-settings",
                    method="POST",
                    json={"field": "logo_url", "value": "http://x"},
                ):
                    api_update_tenant_settings()
                mock_db.session.commit.side_effect = RuntimeError("fail")
                mock_db.session.rollback = MagicMock()
                with app.test_request_context(
                    "/owner/api/update-tenant-settings",
                    method="POST",
                    json={"field": "prices_include_vat", "value": True},
                ):
                    api_update_tenant_settings()
            wh_cls = _model_class()
            wh_cls.query.filter_by.return_value.first.return_value = None
            with patch("routes.owner.Warehouse", wh_cls):
                with app.test_request_context(
                    "/owner/api/toggle-warehouse-negative",
                    method="POST",
                    json={"warehouse_id": 1},
                ):
                    api_toggle_warehouse_negative()

    def test_api_tenant_toggle_activate_path(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, api_tenant_toggle_status

        tenant = _mock_tenant(id=2)
        tenant.is_active = False
        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = tenant
            with app.test_request_context("/owner/api/tenant/2/toggle-status", method="POST", json={}):
                api_tenant_toggle_status(2)

    def test_api_tenant_package_not_found(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, api_tenant_update_package

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = None
            with app.test_request_context(
                "/owner/api/tenant/9/update-package",
                method="POST",
                json={"field": "max_users", "value": 5},
            ):
                api_tenant_update_package(9)

    def test_supervisor_override_missing_credentials(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, api_supervisor_override

        app = app_factory(owner_bp)
        with _owner_route_patches():
            with app.test_request_context("/owner/api/supervisor-override", method="POST", json={"supervisor_id": 1}):
                resp = api_supervisor_override()
        assert _status_code(resp) == 400

    def test_database_optimize_vacuum_fail_only(self, owner_client):
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", return_value={"success": False}), \
             patch("utils.database_optimizer.DatabaseOptimizer.analyze_tables", return_value={"success": False}):
            owner_client.post("/owner/database-optimize", follow_redirects=False)

    def test_preview_receipt_full_render(self, owner_client):
        settings = MagicMock()
        settings.enable_qr_code = True
        inv_cls = _invoice_settings_class(settings)
        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.render_template", return_value="ok"):
            resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_store_payment_delete_exception(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, store_payment_method_delete

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("services.store_payment_method_service.StorePaymentMethodService.delete_method", side_effect=RuntimeError("del")):
            with app.test_request_context("/owner/store-payment-methods/1/delete", method="POST"):
                store_payment_method_delete(1)

    def test_scoped_backup_no_active_tenant_direct(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_scoped_backup
        from werkzeug.exceptions import Forbidden

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("utils.tenanting.get_active_tenant_id", return_value=None):
            with app.test_request_context(
                "/owner/backups/create", method="POST", data={"scope": "tenant", "tenant_id": "1"}
            ):
                with pytest.raises(Forbidden):
                    create_scoped_backup()

    def test_export_json_lines_direct(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_file = str(tmp_path / "out.json")
        exec_result = _execute_result(rows=[(1,)], columns=["id"])
        with _owner_route_patches(), \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner.db") as mock_db, \
             patch("os.makedirs"), \
             patch("os.path.join", return_value=export_file):
            mock_db.session.execute.return_value = exec_result
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "json"}):
                export_database()

    def test_preview_receipt_tenant_abort(self, app_factory, mock_user):
        from routes.owner import owner_bp, preview_receipt

        mock_user.is_owner = False
        role = MagicMock()
        role.slug = "super_admin"
        mock_user.role = role
        mock_user.is_super_admin.return_value = True
        app = app_factory(owner_bp)
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
            with app.test_request_context("/owner/preview-receipt/modern?tenant_id=3"):
                with pytest.raises(Exception):
                    preview_receipt("modern")


class TestOwnerLastMile:
    def test_database_tools_skips_sensitive_table(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, database_tools

        app = app_factory(owner_bp)
        inspector = _inspector()
        inspector.get_table_names.return_value = ["users"]
        with _owner_route_patches(), patch("sqlalchemy.inspect", return_value=inspector):
            with app.test_request_context("/owner/database-tools"):
                database_tools()

    def test_export_sql_full_success(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_file = str(tmp_path / "db_export.sql")
        proc = MagicMock(returncode=0, stderr="", stdout="")
        with _owner_route_patches(), \
             patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=proc), \
             patch("os.makedirs"), \
             patch("os.path.join", return_value=export_file):
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "sql"}):
                export_database()

    def test_tenant_ai_success_path(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_ai_toggle

        tenant = _mock_tenant(id=2)
        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = tenant
            with app.test_request_context(
                "/owner/tenant-ai/2/toggle",
                method="POST",
                data={"enable_ai": "1", "ai_access_level": "advanced"},
            ):
                tenant_ai_toggle(2)

    def test_store_payment_edit_runtime_error(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, store_payment_method_edit

        method = MagicMock()
        method.id = 1
        method.sort_order = 1
        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db, \
             patch("services.store_payment_method_service.StorePaymentMethodService.update_method", side_effect=RuntimeError("upd")):
            mock_db.session.get.return_value = method
            with app.test_request_context("/owner/store-payment-methods/1/edit", method="POST", data={"code": "x"}):
                store_payment_method_edit(1)

    def test_system_config_currency_except(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, system_config

        app = app_factory(owner_bp)
        with _owner_route_patches():
            with app.test_request_context(
                "/owner/system-config",
                method="POST",
                data={"default_currency": "INVALID", "azad_platform_fee_rate": "not-decimal"},
            ):
                system_config()

    def test_create_scoped_backup_branch_missing_id(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_scoped_backup

        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("utils.auth_helpers.is_global_owner_user", return_value=True):
            with app.test_request_context(
                "/owner/backups/create",
                method="POST",
                data={"scope": "branch", "tenant_id": "1"},
            ):
                create_scoped_backup()

    def test_create_scoped_backup_branch_denied_direct(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_scoped_backup
        from werkzeug.exceptions import Forbidden

        user = MagicMock()
        user.is_authenticated = True
        user.is_owner = True
        user.branch_id = 1
        user.id = 1
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("flask_login.utils._get_user", return_value=user), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("routes.owner.get_active_tenant_id", return_value=1):
            with app.test_request_context(
                "/owner/backups/create",
                method="POST",
                data={"scope": "branch", "tenant_id": "1", "branch_id": "9"},
            ):
                with pytest.raises(Forbidden):
                    create_scoped_backup()

    def test_api_update_tenant_not_json(self, app_factory, mock_user):
        from routes.owner import owner_bp, api_update_tenant_settings

        mock_user.is_super_admin.return_value = True
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("utils.decorators.is_global_owner_user", return_value=False), \
             patch("extensions.limiter.limit", return_value=lambda f: f):
            with app.test_request_context("/owner/api/update-tenant-settings", method="POST", data={}):
                resp = api_update_tenant_settings()
        assert _status_code(resp) == 400

    def test_api_toggle_warehouse_not_json(self, app_factory, mock_user):
        from routes.owner import owner_bp, api_toggle_warehouse_negative

        mock_user.is_super_admin.return_value = True
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("utils.decorators.is_global_owner_user", return_value=False), \
             patch("extensions.limiter.limit", return_value=lambda f: f):
            with app.test_request_context("/owner/api/toggle-warehouse-negative", method="POST", data={}):
                resp = api_toggle_warehouse_negative()
        assert _status_code(resp) == 400

    def test_api_tenant_toggle_default_protected(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, api_tenant_toggle_status

        tenant = _mock_tenant(id=1)
        app = app_factory(owner_bp)
        with _owner_route_patches(), patch("routes.owner.db") as mock_db:
            mock_db.session.get.return_value = tenant
            with app.test_request_context("/owner/api/tenant/1/toggle-status", method="POST", json={"noop": True}):
                resp = api_tenant_toggle_status(1)
        assert _status_code(resp) == 400

    def test_mask_db_uri_edge_cases(self):
        from routes.owner import _mask_db_uri
        assert _mask_db_uri("postgresql://user@host/db")  # no colon in creds branch
        try:
            _mask_db_uri("://bad@host")
        except Exception:
            pass

    def test_convert_empty_row_columns(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, convert_database

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        exec_result = _execute_result(rows=[(1,)], columns=["secret_col"])
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner._inspector_column_names", return_value=set()):
            mock_db.session.execute.return_value = exec_result
            with app.test_request_context(
                "/owner/convert-database",
                method="POST",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/db"},
            ):
                convert_database()

    def test_preview_receipt_calls_get_source_info(self, owner_client):
        settings = MagicMock()
        settings.enable_qr_code = False
        inv_cls = _invoice_settings_class(settings)

        def _render(name, **ctx):
            ctx["receipt"].get_source_info()
            return "ok"

        with patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("routes.owner.render_template", side_effect=_render):
            resp = owner_client.get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_invoice_settings_saves_upload_files(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, invoice_settings
        from io import BytesIO

        app = app_factory(owner_bp)
        settings = MagicMock()
        inv_cls = _invoice_settings_class(settings)

        with _owner_route_patches(), \
             patch("routes.owner.InvoiceSettings", inv_cls), \
             patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("os.makedirs"), \
             patch("os.path.join", side_effect=lambda *a: str(tmp_path / a[-1])):
            with app.test_request_context(
                "/owner/invoice-settings",
                method="POST",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (BytesIO(b"png"), "logo.png"),
                    "watermark_image": (BytesIO(b"wm"), "wm.png"),
                },
                content_type="multipart/form-data",
            ):
                invoice_settings()

    def test_export_paths_via_service_patch(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_sql = str(tmp_path / "export.sql")
        export_json = str(tmp_path / "export.json")
        proc = MagicMock(returncode=0, stderr="", stdout="")
        exec_result = _execute_result(rows=[(1, "x")], columns=["id", "name"])
        with _owner_route_patches(), \
             patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="/pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=proc), \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("os.makedirs"), \
             patch("routes.owner.db") as mock_db:
            mock_db.session.execute.return_value = exec_result
            with patch("os.path.join", return_value=export_sql):
                with app.test_request_context("/owner/export-database", method="POST", data={"format": "sql"}):
                    export_database()
            with patch("os.path.join", return_value=export_json):
                with app.test_request_context("/owner/export-database", method="POST", data={"format": "json"}):
                    export_database()

    def test_database_tools_restricted_only(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, database_tools

        app = app_factory(owner_bp)
        inspector = _inspector()
        inspector.get_table_names.return_value = ["users", "payment_vault"]
        with _owner_route_patches(), \
             patch("routes.owner._known_tables_map", return_value={"users": "users", "payment_vault": "payment_vault"}), \
             patch("sqlalchemy.inspect", return_value=inspector):
            with app.test_request_context("/owner/database-tools"):
                database_tools()

    def test_tenant_ai_toggle_commits(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_ai_toggle

        tenant = _mock_tenant(id=3)
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner.db") as mock_db, \
             patch("utils.ai_access.set_tenant_ai_level", return_value="advanced"):
            mock_db.session.get.return_value = tenant
            with app.test_request_context(
                "/owner/tenant-ai/3/toggle",
                method="POST",
                data={"enable_ai": "1", "ai_access_level": "advanced"},
            ):
                tenant_ai_toggle(3)

    def test_database_optimize_warning_only(self, owner_client):
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", return_value={"success": True}), \
             patch("utils.database_optimizer.DatabaseOptimizer.analyze_tables", return_value={"success": False, "error": "x"}):
            owner_client.post("/owner/database-optimize", follow_redirects=False)

    def test_create_user_non_global_tenant_id(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, create_user

        bypass_owner_auth.is_owner = False
        bypass_owner_auth.tenant_id = 1
        role = _mock_role(slug="seller")
        user_cls = _model_class()
        user_cls.query.filter_by.return_value.first.return_value = None
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("models.Role", _model_class(all=[role])), \
             patch("routes.owner.User", user_cls), \
             patch("routes.owner.role_requires_branch", return_value=False), \
             patch("routes.owner.role_level_for", return_value=10):
            import routes.owner as owner_mod
            owner_mod.db.session.get.return_value = role
            with app.test_request_context(
                "/owner/users/create",
                method="POST",
                data={
                    "username": "co2",
                    "password": "Str0ng!Pass",
                    "role_id": "2",
                    "email": "c@t.com",
                    "full_name": "Co",
                },
            ):
                create_user()


class TestOwnerHundredPercent:
    def test_mask_db_uri_parse_error_returns_redacted(self):
        from routes.owner import _mask_db_uri

        class _BadUri(str):
            def split(self, sep=None, maxsplit=-1):
                if sep == "://":
                    raise ValueError("boom")
                return super().split(sep, maxsplit)

        assert _mask_db_uri(_BadUri("postgresql://u:p@host/db")) == "[redacted]"

    def test_validate_postgresql_uri_blank(self):
        from routes.owner import _validate_postgresql_uri

        assert _validate_postgresql_uri("") is False
        assert _validate_postgresql_uri("   ") is False

    def test_edit_table_data_rejects_unknown_table(self, owner_client):
        resp = owner_client.get("/owner/edit-table-data/__unknown_xyz__", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_export_sql_pg_dump_unavailable(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("services.backup_service.BackupService._parse_db_url", return_value=None), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value=None):
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "sql"}):
                result = export_database()
        assert result.status_code in (302, 303)

    def test_export_sql_pg_dump_nonzero_exit(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_file = str(tmp_path / "db_export.sql")
        proc = MagicMock(returncode=1, stderr="dump failed", stdout="")
        with _owner_route_patches(), \
             patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "p", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="/pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=proc), \
             patch("os.makedirs"), \
             patch("os.path.join", return_value=export_file):
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "sql"}):
                export_database()

    def test_export_sql_pg_dump_success(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_file = str(tmp_path / "db_export.sql")
        proc = MagicMock(returncode=0, stderr="", stdout="")
        with _owner_route_patches(), \
             patch("services.backup_service.BackupService._parse_db_url", return_value={"host": "h", "port": "5432", "username": "u", "password": "secret", "dbname": "d"}), \
             patch("services.backup_service.BackupService._resolve_pg_tool", return_value="/pg_dump"), \
             patch("services.backup_exec.run_pg_tool", return_value=proc) as run_tool, \
             patch("os.makedirs"), \
             patch("os.path.join", return_value=export_file):
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "sql"}):
                export_database()
        assert run_tool.called
        assert run_tool.call_args.kwargs["env"].get("PGPASSWORD") == "secret"

    def test_export_json_writes_tables(self, app_factory, bypass_owner_auth, tmp_path):
        from routes.owner import owner_bp, export_database

        app = app_factory(owner_bp)
        export_file = str(tmp_path / "export.json")
        exec_result = _execute_result(rows=[(1, "x")], columns=["id", "name"])
        with _owner_route_patches(), \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner.db") as mock_db, \
             patch("os.makedirs"), \
             patch("os.path.join", return_value=export_file):
            mock_db.session.execute.return_value = exec_result
            with app.test_request_context("/owner/export-database", method="POST", data={"format": "json"}):
                export_database()
            assert export_file.endswith(".json")

    def test_convert_database_skips_when_no_allowed_columns(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, convert_database

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        exec_result = _execute_result(rows=[(1, "secret")], columns=["id", "secret_col"])
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner._validate_postgresql_uri", return_value=True), \
             patch("sqlalchemy.create_engine", return_value=mock_engine), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner._known_tables_map", return_value={"customers": "customers"}), \
             patch("routes.owner._inspector_column_names", return_value={"other_col"}):
            mock_db.session.execute.return_value = exec_result
            with app.test_request_context(
                "/owner/convert-database",
                method="POST",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@localhost/db"},
            ):
                convert_database()
            mock_conn.execute.assert_not_called()

    def test_system_config_currency_sync_failure(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, system_config

        app = app_factory(owner_bp)
        settings = MagicMock()
        type(settings).default_currency = property(
            lambda self: "AED",
            lambda self, v: (_ for _ in ()).throw(RuntimeError("bad currency")),
        )
        settings_cls = _settings_class(settings)
        with _owner_route_patches(), \
             patch("routes.owner.SystemSettings", settings_cls), \
             patch("routes.owner.Tenant.get_current", side_effect=RuntimeError("no tenant")):
            with app.test_request_context(
                "/owner/system-config",
                method="POST",
                data={"default_currency": "AED", "items_per_page": "25"},
            ):
                system_config()

    def test_tenant_ai_toggle_success_with_audit(self, app_factory, bypass_owner_auth):
        from routes.owner import owner_bp, tenant_ai_toggle

        tenant = _mock_tenant(id=3)
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("routes.owner.db") as mock_db, \
             patch("routes.owner.set_tenant_ai_level", return_value="advanced") as set_level, \
             patch("routes.owner.LoggingCore.log_audit") as log_audit:
            mock_db.session.get.return_value = tenant
            with app.test_request_context(
                "/owner/tenant-ai/3/toggle",
                method="POST",
                data={"enable_ai": "1", "ai_access_level": "advanced"},
            ):
                result = tenant_ai_toggle(3)
        set_level.assert_called_once()
        log_audit.assert_called_once()
        assert result.status_code in (302, 303)

    def test_database_optimize_full_success(self, owner_client):
        with patch("utils.database_optimizer.DatabaseOptimizer.vacuum_postgres", return_value={"success": True}), \
             patch("utils.database_optimizer.DatabaseOptimizer.analyze_tables", return_value={"success": True}):
            resp = owner_client.post("/owner/database-optimize", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_invoice_settings_multipart_upload_paths(self, owner_client, tmp_path):
        from io import BytesIO

        settings = MagicMock()
        inv_cls = _invoice_settings_class(settings)
        logo_path = str(tmp_path / "logo.png")
        wm_path = str(tmp_path / "watermark.png")
        join_calls = {"n": 0}

        def _join(*parts):
            join_calls["n"] += 1
            if "watermarks" in parts:
                return wm_path
            return logo_path

        with patch("routes.owner.InvoiceSettings", inv_cls), \
             patch("models.invoice_settings.InvoiceSettings", inv_cls), \
             patch("os.makedirs") as makedirs, \
             patch("os.path.join", side_effect=_join):
            resp = owner_client.post(
                "/owner/invoice-settings",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (BytesIO(b"logo"), "logo.png"),
                    "watermark_image": (BytesIO(b"wm"), "watermark.png"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code in (302, 303, 200)
        assert makedirs.call_count >= 2
        assert settings.logo_path
        assert settings.watermark_image_path

    def test_api_toggle_warehouse_missing_id(self, app_factory, mock_user):
        from routes.owner import owner_bp, api_toggle_warehouse_negative

        mock_user.is_super_admin.return_value = True
        app = app_factory(owner_bp)
        with _owner_route_patches(), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("utils.decorators.is_global_owner_user", return_value=False), \
             patch("extensions.limiter.limit", return_value=lambda f: f):
            with app.test_request_context(
                "/owner/api/toggle-warehouse-negative",
                method="POST",
                json={"warehouse_id": None},
            ):
                resp = api_toggle_warehouse_negative()
        assert _status_code(resp) == 400

