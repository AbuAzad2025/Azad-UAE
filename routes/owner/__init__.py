"""Owner blueprint package — routes split into sub-modules for maintainability."""

import logging

# ── Re-exports (for testing + shared access across sub-modules) ──────────────
# These are defined here before sub-module imports so sub-modules can import
# from `routes.owner` instead of importing directly from flask/models/utils.
# This allows the test suite's `patch("routes.owner.X")` to intercept calls
# made inside any sub-module.
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import desc, func, inspect, text

from extensions import db, limiter
from models import (
    ArchivedRecord,
    AuditLog,
    Branch,
    CardVault,
    Customer,
    Donation,
    Expense,
    IntegrationSettings,
    InvoiceSettings,
    Payment,
    Product,
    ProductReturn,
    Purchase,
    Receipt,
    Role,
    Sale,
    SaleLine,
    StockMovement,
    SystemSettings,
    Tenant,
    User,
    Warehouse,
)
from models.api_key import APIKey
from models.exchange_rate_record import ExchangeRateRecord
from models.login_history import LoginHistory
from models.payment_vault import PaymentVault
from models.product_warehouse_cost import ProductWarehouseCost
from models.security_alert import SecurityAlert
from models.store_payment_method import StorePaymentMethod
from models.tenant_store import TenantStore
from utils.ai_access import get_tenant_ai_level, set_tenant_ai_level
from utils.auth_helpers import (
    enforce_company_user_tenant,
    is_global_owner_user,
    role_level_for,
    role_level_for_user,
    user_may_have_null_tenant,
)
from utils.branching import get_visible_products_query, role_requires_branch
from utils.currency_utils import get_system_default_currency, resolve_default_currency
from utils.decorators import (
    company_admin_required,
    owner_or_company_admin,
    owner_required,
    permission_required,
)
from utils.safe_redirect import safe_redirect_target
from utils.sanitizer import InputSanitizer
from utils.tenanting import get_active_tenant_id

# Import sub-modules so they register their routes on the shared owner_bp.
# Each sub-module is loaded here to ensure all @owner_bp.route decorators fire.
from . import backups, core, database, maintenance, monitoring, settings, shared, tenants, users

# Re-export route handler names so `from routes.owner import X` works
# (matching the flat-module API from pre-refactoring routes/owner.py).
from .backups import create_scoped_backup, restore_backup_target
from .blueprint import owner_bp
from .database import (
    convert_database,
    database_tools,
    edit_table_data,
    export_database,
    sql_console,
)
from .settings import (
    api_supervisor_override,
    api_toggle_warehouse_negative,
    api_update_tenant_settings,
    invoice_settings,
    preview_receipt,
    store_payment_method_create,
    store_payment_method_delete,
    store_payment_method_edit,
    store_payment_method_toggle,
    system_config,
)

# Re-export shared helpers that tests patch via "routes.owner.*"
from .shared import (
    _audit_owner_db_action,
    _inspector_column_names,
    _invalidate_owner_changes,
    _is_sensitive_stats_table,
    _known_tables_map,
    _mask_api_key,
    _mask_db_uri,
    _owner_branch_scope,
    _resolve_browsable_table,
    _resolve_known_table,
    _resolve_truncatable_table,
    _validate_postgresql_uri,
    _validate_select_only_sql,
)
from .tenants import (
    api_tenant_toggle_status,
    api_tenant_update_package,
    tenant_ai_toggle,
    tenant_store_platform_toggle,
)
from .users import create_user

logger = logging.getLogger(__name__)


@owner_bp.before_request
def _owner_ip_guard():
    from utils.security_helpers import enforce_owner_ip_if_needed

    enforce_owner_ip_if_needed()


__all__ = [
    "shared",
    "core",
    "tenants",
    "users",
    "backups",
    "database",
    "settings",
    "monitoring",
    "maintenance",
    "render_template",
    "request",
    "jsonify",
    "flash",
    "redirect",
    "url_for",
    "current_app",
    "abort",
    "login_required",
    "current_user",
    "func",
    "desc",
    "text",
    "inspect",
    "db",
    "limiter",
    "User",
    "Customer",
    "Product",
    "Sale",
    "SaleLine",
    "Purchase",
    "Payment",
    "Receipt",
    "StockMovement",
    "AuditLog",
    "ArchivedRecord",
    "ProductReturn",
    "CardVault",
    "InvoiceSettings",
    "Tenant",
    "SystemSettings",
    "IntegrationSettings",
    "Expense",
    "Branch",
    "Warehouse",
    "Role",
    "Donation",
    "LoginHistory",
    "SecurityAlert",
    "APIKey",
    "TenantStore",
    "ExchangeRateRecord",
    "PaymentVault",
    "ProductWarehouseCost",
    "StorePaymentMethod",
    "owner_required",
    "permission_required",
    "company_admin_required",
    "owner_or_company_admin",
    "role_requires_branch",
    "get_visible_products_query",
    "role_level_for",
    "role_level_for_user",
    "is_global_owner_user",
    "user_may_have_null_tenant",
    "enforce_company_user_tenant",
    "get_active_tenant_id",
    "get_system_default_currency",
    "resolve_default_currency",
    "get_tenant_ai_level",
    "set_tenant_ai_level",
    "safe_redirect_target",
    "InputSanitizer",
    "_known_tables_map",
    "_validate_postgresql_uri",
    "_mask_api_key",
    "_mask_db_uri",
    "_resolve_known_table",
    "_resolve_truncatable_table",
    "_resolve_browsable_table",
    "_validate_select_only_sql",
    "_is_sensitive_stats_table",
    "_inspector_column_names",
    "_owner_branch_scope",
    "_invalidate_owner_changes",
    "_audit_owner_db_action",
    "create_scoped_backup",
    "restore_backup_target",
    "database_tools",
    "edit_table_data",
    "sql_console",
    "export_database",
    "convert_database",
    "system_config",
    "store_payment_method_create",
    "store_payment_method_edit",
    "store_payment_method_toggle",
    "store_payment_method_delete",
    "invoice_settings",
    "preview_receipt",
    "api_update_tenant_settings",
    "api_toggle_warehouse_negative",
    "api_supervisor_override",
    "tenant_ai_toggle",
    "tenant_store_platform_toggle",
    "api_tenant_toggle_status",
    "api_tenant_update_package",
    "create_user",
]
