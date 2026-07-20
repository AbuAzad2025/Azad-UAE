"""
tests/unit/conftest.py — Isolated route unit tests (zero database dependency).
Every fixture mocks auth, DB, and service layers so tests run instantly.
"""

# Re-export DB fixtures from parent conftest for --confcutdir=tests/unit runs.
from tests.conftest import (
    _reset_rate_limiter,
    _restore_session_app_config,
    app,
    auth_client,
    auto_cleanup_isolation,
    client,
    db_session,
    logged_in_client,
    owner_client,
    runner,
    sample_branch,
    sample_cheque,
    sample_currency_aed,
    sample_customer,
    sample_employee,
    sample_expense,
    sample_expense_category,
    sample_gl_accounts,
    sample_owner,
    sample_payroll_transaction,
    sample_permissions,
    sample_product,
    sample_product_with_stock,
    sample_purchase,
    sample_role,
    sample_sale,
    sample_supplier,
    sample_tenant,
    sample_user,
    sample_warehouse,
)

__all__ = [
    "_reset_rate_limiter",
    "_restore_session_app_config",
    "app",
    "auth_client",
    "auto_cleanup_isolation",
    "client",
    "db_session",
    "logged_in_client",
    "owner_client",
    "runner",
    "sample_branch",
    "sample_cheque",
    "sample_currency_aed",
    "sample_customer",
    "sample_employee",
    "sample_expense",
    "sample_expense_category",
    "sample_gl_accounts",
    "sample_owner",
    "sample_payroll_transaction",
    "sample_permissions",
    "sample_product",
    "sample_product_with_stock",
    "sample_purchase",
    "sample_role",
    "sample_sale",
    "sample_supplier",
    "sample_tenant",
    "sample_user",
    "sample_warehouse",
]

import pytest
from flask import Flask
from unittest.mock import MagicMock

# Python 3.14 + pytest-cov can import SQLAlchemy twice; tolerate duplicate inspect registration.
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
    """Preload SQLAlchemy ORM under pytest-cov to avoid partial module state on Python 3.14."""
    if not config.pluginmanager.hasplugin("_cov"):
        return
    import importlib

    import sqlalchemy.orm.dependency as _dep

    if not hasattr(_dep, "_direction_to_processor"):
        importlib.reload(_dep)


# ---------------------------------------------------------------------------
# App & client factories
# ---------------------------------------------------------------------------


@pytest.fixture
def app_factory():
    def _create_app(blueprint, config_overrides=None):
        import sys
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        from tests.conftest import TestConfig

        _app = Flask(__name__, template_folder=os.path.join(project_root, "templates"))
        _app.config.from_object(TestConfig)
        if config_overrides:
            _app.config.update(config_overrides)
        from extensions import db, babel, get_locale

        db.init_app(_app)
        babel.init_app(_app, locale_selector=get_locale)
        from flask_login import current_user

        _app.jinja_env.globals["current_user"] = current_user
        from utils.i18n import t

        _app.jinja_env.globals["t"] = t
        _app.jinja_env.globals["csrf_token"] = lambda: ""
        _app.register_blueprint(blueprint)
        from routes.main import main_bp

        if "main" not in _app.blueprints:
            _app.register_blueprint(main_bp)
        return _app

    return _create_app


# ---------------------------------------------------------------------------
# Generic authenticated user (route tests under tests/unit/routes/)
# ---------------------------------------------------------------------------


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
    role = MagicMock()
    role.slug = "super_admin"
    user.role = role
    return user


# ---------------------------------------------------------------------------
# Auth bypass fixtures  (/owner/* routes)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_owner_user(mocker):
    user = mocker.MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_owner = True
    user.tenant_id = None
    user.id = 1
    user.username = "owner-test"
    user.email = "owner@test.com"
    user.full_name = "Test Platform Owner"
    user.branch_id = None
    return user


@pytest.fixture
def bypass_owner_auth(mocker, mock_owner_user):
    mocker.patch("flask_login.utils._get_user", return_value=mock_owner_user)
    mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
    mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=True)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.security_helpers.enforce_owner_ip_if_needed", return_value=None)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
    mocker.patch("utils.branching.get_active_branch_id", return_value=None)


@pytest.fixture
def mock_owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    _app = app_factory(owner_bp)
    return _app.test_client()


# ---------------------------------------------------------------------------
# Company-admin client  (for @company_admin_required endpoints)
# ---------------------------------------------------------------------------


@pytest.fixture
def bypass_company_admin_auth(mocker, mock_owner_user):
    """
    Bypass @company_admin_required + @login_required for company-level routes.

    Does NOT patch ``company_admin_required`` itself (that decorator is already
    applied at import time).  Instead, it patches the runtime checks the
    decorator performs: ``is_global_owner_user`` returns ``False``, the user
    mock has ``is_super_admin()`` returning a truthy, and
    ``get_active_tenant_id`` returns a valid tenant id.
    """
    mock_owner_user.is_super_admin.return_value = True
    mocker.patch("flask_login.utils._get_user", return_value=mock_owner_user)
    mocker.patch("utils.decorators.is_global_owner_user", return_value=False)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)


@pytest.fixture
def mock_company_admin_client(app_factory, bypass_company_admin_auth):
    from routes.owner import owner_bp

    _app = app_factory(owner_bp)
    return _app.test_client()


# ---------------------------------------------------------------------------
# Payment-vault owner client  (/payment-vault/* routes)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vault_owner_client(app_factory, bypass_owner_auth):
    from routes.payment_vault import payment_vault_bp

    _app = app_factory(payment_vault_bp)
    return _app.test_client()


# ---------------------------------------------------------------------------
# Product client  (/products/* routes)
# ---------------------------------------------------------------------------


@pytest.fixture
def bypass_product_auth(mocker):
    """Bypass @login_required + @permission_required on /products/* routes."""
    user = mocker.MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.has_permission.return_value = True
    user.tenant_id = 1
    user.id = 42
    user.branch_id = None

    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
    return user


@pytest.fixture
def product_client(app_factory, bypass_product_auth):
    from routes.products import products_bp

    _app = app_factory(products_bp)
    return _app.test_client()


# ---------------------------------------------------------------------------
# AI route fixtures  (/ai/* routes)
# ---------------------------------------------------------------------------


@pytest.fixture
def bypass_ai_access(mocker):
    """
    Bypass AI access-policy enforcement, login, and permission checks
    for ``/ai/*`` routes.

    Patches:
    * ``flask_login.utils._get_user`` – returns a regular authenticated user
      whose ``has_permission`` returns ``True`` for any permission code.
    * ``routes.ai_routes.get_ai_access_state`` – returns a fully permissive state so
      the ``_enforce_ai_access_policy`` before-request handler always passes.
    * ``utils.auth_helpers.is_global_owner_user`` – returns ``True`` so the
      ``permission_required`` decorator skips actual permission checks.
    * ``extensions.limiter.limit`` – no-op decorator.
    * ``utils.tenanting.get_active_tenant_id`` – returns ``1``.
    """
    user = mocker.MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_owner = False
    user.tenant_id = 1
    user.id = 42
    user.username = "ai-test-user"
    user.email = "ai@test.com"
    user.full_name = "AI Test User"
    user.has_permission.return_value = True

    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch(
        "routes.ai_routes.get_ai_access_state",
        return_value={
            "allowed": True,
            "global_enabled": True,
            "tenant_enabled": True,
            "tenant_id": 1,
            "reason": None,
            "is_platform_user": True,
            "ai_level": "execute",
        },
    )
    mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=True)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)

    return user


@pytest.fixture
def model_patch(mocker):
    """
    Fixture factory that patches a model path and returns the MagicMock.

    Usage::

        Partner = model_patch("models.Partner", count=len(partners))
        Partner.query.filter_by.return_value.all.return_value = partners
    """

    def _patch(model_path: str, count: int = 0):
        return mocker.patch(model_path)

    return _patch


@pytest.fixture
def mock_db_query():
    return MagicMock()


@pytest.fixture
def mock_db_connection(mocker):
    """
    Fixture factory that creates a mocked database connection.

    Usage::

        conn = mock_db_connection(scalar=42)
        conn.execute.side_effect = [...]

    Supports ``scalar``, ``rows``, and ``keys`` keyword arguments
    to pre-configure ``conn.execute().scalar()`` or iterator results.
    """

    def _make(scalar=None, rows=None, keys=None):
        conn = mocker.MagicMock()
        conn.execute.return_value.scalar.return_value = scalar
        if rows is not None:
            result = mocker.MagicMock()
            result.__iter__.return_value = iter(rows)
            result.fetchall.return_value = rows
            if keys is not None:
                result.keys.return_value = keys
            conn.execute.return_value = result
        return conn

    return _make


@pytest.fixture
def mock_db(mocker):
    """Central mock that replaces ``db.session`` globally with a ``MagicMock``.

    Every module that does ``from extensions import db; db.session.X`` will
    transparently receive this mock, preventing real database access across
    all service, route, and model unit tests.

    The returned object is a self-referencing ``MagicMock`` — its ``.session``
    attribute points to itself — so both ``mock_db.commit()`` and
    ``mock_db.session.commit()`` resolve to the same mock, and tests written
    for either pattern work without changes.

    Usage
    -----
    Tests that need to configure the session mock accept ``mock_db`` as a
    fixture parameter::

        def test_something(self, mock_db):
            mock_db.commit.side_effect = RuntimeError("db fail")
            mock_db.query.side_effect = lambda *a: [...]

    Tests that only need the side effect (preventing real DB calls) can
    either accept the fixture or use a file-level ``pytestmark``::

        pytestmark = pytest.mark.usefixtures("mock_db")
    """
    mock = mocker.MagicMock(name="global_mock_db")
    # Session-level methods (configured explicitly so property resolution
    # doesn't fall through to ``__getattr__`` which would break patching).
    mock.add = mocker.MagicMock()
    mock.flush = mocker.MagicMock()
    mock.delete = mocker.MagicMock()
    mock.commit = mocker.MagicMock()
    mock.rollback = mocker.MagicMock()
    # Query / execute helpers
    mock.query = mocker.MagicMock()
    mock.execute = mocker.MagicMock()
    mock.get = mocker.MagicMock()
    mock.scalar = mocker.MagicMock()
    # DB-level attributes
    mock.engine = mocker.MagicMock()
    # Self-referencing .session so ``mock_db.session.commit`` and ``mock_db.commit``
    # both reach the same mock.
    mock.session = mock

    # ── Global patching ──────────────────────────────────────────────────
    # Patch ``extensions.db.session`` (the root reference) so every import
    # of ``db`` from ``extensions`` picks up the mocked session.
    mocker.patch("extensions.db.session", mock)
    # Explicit per-module patches for modules that were imported before the
    # fixture ran and thus hold a local ``db`` reference in their namespace.
    mocker.patch("services.crm_lead_service.db.session", mock)
    mocker.patch("routes.payment_vault.db.session", mock)

    return mock


@pytest.fixture
def mock_ai_service(mocker):
    """
    Patch ``routes.ai_routes.AIService`` static methods so tests never hit a real
    AI/LLM backend.

    Provides separate mocks for each method used by Chunk-1 endpoints::

        mock_ai_service.recommend_price       # AIService.recommend_price
        mock_ai_service.check_stock_alert     # AIService.check_stock_alert
        mock_ai_service.analyze_customer      # AIService.analyze_customer_behavior

    Each mock is pre-configured with sensible default return values. Override
    in individual tests::

        mock_ai_service.recommend_price.return_value = {"recommended_price": 99.0, ...}
        mock_ai_service.recommend_price.side_effect = TimeoutError("API timeout")
    """
    recommend_price = mocker.patch("routes.ai_routes.AIService.recommend_price")
    check_stock = mocker.patch("routes.ai_routes.AIService.check_stock_alert")
    analyze_customer = mocker.patch("routes.ai_routes.AIService.analyze_customer_behavior")

    return type(
        "MockAIService",
        (),
        {
            "recommend_price": recommend_price,
            "check_stock_alert": check_stock,
            "analyze_customer_behavior": analyze_customer,
        },
    )


@pytest.fixture
def ai_client(app_factory, bypass_ai_access):
    """Test client with the ``ai`` blueprint registered."""
    from routes.ai_routes import ai_bp

    _app = app_factory(ai_bp)
    return _app.test_client()
