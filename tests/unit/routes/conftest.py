import warnings
from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from itertools import cycle
import sys
from unittest.mock import MagicMock, patch

warnings.filterwarnings("ignore", message="coroutine 'AsyncMockMixin._execute_mock_call' was never awaited")

import pytest
from flask import Flask, make_response
from flask_login import login_user, logout_user

for _mod in ('numpy', 'pandas'):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except Exception:
            sys.modules[_mod] = MagicMock()

try:
    import sqlalchemy.inspection as _sa_inspection
    _orig_inspects_factory = _sa_inspection._inspects

    def _safe_inspects(*types):
        _orig_decorator = _orig_inspects_factory(*types)
        def decorate(fn_or_cls):
            try:
                return _orig_decorator(fn_or_cls)
            except AssertionError as exc:
                if "already registered" in str(exc):
                    return fn_or_cls
                raise
        return decorate

    _sa_inspection._inspects = _safe_inspects
except Exception:
    pass
def pytest_configure(config):
    if not config.pluginmanager.hasplugin('_cov'):
        return
    import importlib
    import sqlalchemy.orm.dependency as _dep
    if not hasattr(_dep, '_direction_to_processor'):
        importlib.reload(_dep)
    from routes.cheques import cheques_bp
    from routes.ledger import ledger_bp
    from routes.reports import reports_bp
    from routes.users import users_bp
    from routes.tenants import tenants_bp
    from routes.branches import branches_bp
    from routes.suppliers import suppliers_bp
    from routes.products import products_bp
    from routes.warehouse import warehouse_bp
    from routes.treasury import treasury_bp
    from routes.payroll import payroll_bp
    from routes.advanced_ledger import advanced_ledger_bp
    from routes.admin_ledger import admin_ledger_bp
    from routes.monitoring import monitoring_bp
    from routes.api_docs import api_docs_bp
    from routes.graphql import graphql_bp
    from routes.api_analytics import api_analytics_bp
    from routes.gamification import gamification_bp
    from routes.ai_routes import ai_bp
    from routes.whatsapp import whatsapp_bp
    from routes.public import public_bp as public_pages_bp
    from routes.owner_admin import owner_admin_bp as owner_control_bp
    from routes.payment_vault import payment_vault_bp
    from routes.shop import shop_bp
    from routes.store import store_bp
    from routes.language import language_bp
    from routes.api import api_bp
    from routes.crm import crm_bp
    from routes.returns import returns_bp
    from routes.projects import projects_bp
    from routes.pos import pos_bp
    from routes.printing import printing_bp
    from routes.email_marketing import email_marketing_bp
    from routes.partners import partners_bp
    from routes.hr import hr_bp
    from routes.tickets import tickets_bp
    from routes.billing_webhooks import billing_webhook_bp as billing_webhooks_bp
    from routes.api_enhanced import api_enhanced_bp
    from routes.websocket import websocket_bp
    
    blueprints = [
        auth_bp, customers_bp, sales_bp, purchases_bp, unified_inventory_bp,
        payments_bp, expenses_bp, cheques_bp, ledger_bp, reports_bp,
        users_bp, tenants_bp, branches_bp, suppliers_bp, products_bp,
        warehouse_bp, treasury_bp, payroll_bp, advanced_ledger_bp,
        admin_ledger_bp, monitoring_bp, api_docs_bp, graphql_bp,
        api_analytics_bp, gamification_bp, ai_bp, whatsapp_bp,
        public_pages_bp, owner_control_bp, payment_vault_bp, shop_bp,
        store_bp, language_bp, api_bp, crm_bp, returns_bp, projects_bp,
        pos_bp, printing_bp, email_marketing_bp, partners_bp, hr_bp,
        tickets_bp, billing_webhooks_bp, api_enhanced_bp, websocket_bp
    ]
    
    for bp in blueprints:
        if bp and bp.name not in app.blueprints:
            app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

# ─── REAL AUTHENTICATION HELPERS ───
def _create_test_user(db_session, tenant_id=1, username="testuser", email="test@example.com", 
                       is_owner=False, is_admin=True, permissions=None):
    """Create a real user in the test database."""
    from models import User, Tenant, Role, Permission, Branch
    
    tenant = db_session.get(Tenant, tenant_id)
    if not tenant:
        tenant = Tenant(
            id=tenant_id,
            name=f"Test Tenant {tenant_id}",
            name_ar="مستأجر اختبار",
            slug=f"test-tenant-{tenant_id}",
            email=f"tenant{tenant_id}@example.com",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
    
    role = db_session.query(Role).filter_by(slug="super_admin" if is_admin else "manager").first()
    if not role:
        role = Role(name="Super Admin" if is_admin else "Manager", slug="super_admin" if is_admin else "manager", is_active=True)
        db_session.add(role)
        db_session.flush()
    
    # Default permissions for test users
    default_perms = ['manage_customers', 'manage_sales', 'manage_purchases', 'manage_inventory', 
                     'manage_payments', 'manage_expenses', 'view_reports', 'manage_products',
                     'manage_warehouse', 'manage_suppliers', 'manage_branches', 'admin']
    perm_codes = permissions if permissions else default_perms
    
    for perm_code in perm_codes:
        perm = db_session.query(Permission).filter_by(code=perm_code).first()
        if not perm:
            perm = Permission(code=perm_code, name=perm_code, name_ar=perm_code, category="test")
            db_session.add(perm)
            db_session.flush()
        # Check if permission is already assigned to role
        if perm not in role.permissions:
            role.permissions.append(perm)
    
    branch = db_session.query(Branch).filter_by(tenant_id=tenant_id, is_main=True).first()
    if not branch:
        branch = Branch(tenant_id=tenant_id, name="Main Branch", code="MAIN", is_active=True, is_main=True)
        db_session.add(branch)
        db_session.flush()
    
    user = User(
        username=username,
        email=email,
        full_name="Test User",
        tenant_id=tenant_id,
        role_id=role.id,
        branch_id=branch.id,
        is_active=True,
        is_owner=is_owner,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()
    return user

def login_user_via_client(client, username="testuser", password="password123"):
    return client.post('/auth/login', data={
        'username': username,
        'password': password,
    }, follow_redirects=True)

def logout_user_via_client(client):
    return client.get('/auth/logout', follow_redirects=True)

# Compatibility shims for older tests
@pytest.fixture
def mock_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_owner = False
    user.tenant_id = 1
    user.id = 42
    user.username = "route-test-user"
    user.email = "route@test.com"
    user.full_name = "Route Test User"
    user.branch_id = None
    user.has_permission.return_value = True
    user.is_admin.return_value = True
    user.is_super_admin.return_value = True
    user.is_seller.return_value = False
    user.can_see_costs.return_value = True
    user.role.slug = "super_admin"
    return user

def _base_auth_patches(mock_user, is_global_owner=True, is_admin_surface=True):
    return [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("utils.auth_helpers.is_global_owner_user", return_value=is_global_owner),
        patch("utils.decorators.is_global_owner_user", return_value=is_global_owner),
        patch("utils.decorators.is_admin_surface_user", return_value=is_admin_surface),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("utils.security_helpers.enforce_owner_ip_if_needed"),
        patch("services.logging_core.LoggingCore.log_audit"),
    ]

@pytest.fixture
def bypass_permission_auth(mock_user):
    patches = _base_auth_patches(mock_user) + [
        patch("utils.decorators.branch_scope_id", return_value=None),
        patch("utils.decorators.report_branch_scope_id", return_value=None),
    ]
    for p in patches: p.start()
    yield mock_user
    for p in reversed(patches): p.stop()

@pytest.fixture
def bypass_admin_auth(mock_user):
    patches = _base_auth_patches(mock_user)
    for p in patches: p.start()
    yield mock_user
    for p in reversed(patches): p.stop()

@pytest.fixture
def bypass_owner_auth(mock_user):
    mock_user.is_owner = True
    patches = _base_auth_patches(mock_user, is_global_owner=True, is_admin_surface=True)
    for p in patches: p.start()
    yield mock_user
    for p in reversed(patches): p.stop()

@pytest.fixture
def bypass_ai_access(mock_user):
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("routes.ai_routes.get_ai_access_state", return_value={
            "allowed": True, "global_enabled": True, "tenant_enabled": True,
            "tenant_id": 1, "reason": None, "is_platform_user": True, "ai_level": "execute",
        }),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_admin_surface_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("services.logging_core.LoggingCore.log_audit"),
    ]
    for p in patches: p.start()
    yield mock_user
    for p in reversed(patches): p.stop()