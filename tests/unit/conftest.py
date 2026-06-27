"""
tests/unit/conftest.py — Isolated route unit tests (zero database dependency).
Every fixture mocks auth, DB, and service layers so tests run instantly.
"""
import sys
from datetime import datetime
from decimal import Decimal
from itertools import cycle

import pytest
from flask import Flask
from unittest.mock import MagicMock

# Stub heavy optional deps before route/model imports under pytest-cov.
for _mod in ('numpy', 'pandas'):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

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
    """Pre-load SQLAlchemy ORM under pytest-cov to avoid partial module state on Python 3.14."""
    if not config.pluginmanager.hasplugin('_cov'):
        return
    import importlib

    import sqlalchemy.orm.dependency as _dep

    if not hasattr(_dep, '_direction_to_processor'):
        importlib.reload(_dep)


# ---------------------------------------------------------------------------
# App & client factories
# ---------------------------------------------------------------------------

@pytest.fixture
def app_factory():
    def _create_app(blueprint, config_overrides=None):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            WTF_CSRF_ENABLED=False,
            DEBUG=True,
            JSON_AS_ASCII=False,
            JSON_SORT_KEYS=False,
            SERVER_NAME="test.local",
        )
        if config_overrides:
            app.config.update(config_overrides)
        app.register_blueprint(blueprint)
        return app
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
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp
    app = app_factory(owner_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Company-admin client  (for @company_admin_required endpoints)
# ---------------------------------------------------------------------------

@pytest.fixture
def bypass_company_admin_auth(mocker, mock_owner_user):
    """
    Bypass @company_admin_required + @login_required for company-level routes.

    Does NOT patch ``company_admin_required`` itself (that decorator is already
    applied at import time).  Instead it patches the runtime checks the
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
def company_admin_client(app_factory, bypass_company_admin_auth):
    from routes.owner import owner_bp
    app = app_factory(owner_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Payment-vault owner client  (/payment-vault/* routes)
# ---------------------------------------------------------------------------

@pytest.fixture
def vault_owner_client(app_factory, bypass_owner_auth):
    from routes.payment_vault import payment_vault_bp
    app = app_factory(payment_vault_bp)
    return app.test_client()


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
    app = app_factory(products_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Reusable mock helpers for route tests
# ---------------------------------------------------------------------------

# Safe defaults for model column attributes used in filter comparisons.
_SAFE_COLUMNS = {
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
    "sale_date": datetime(2020, 1, 1),
    "purchase_date": datetime(2020, 1, 1),
    "sale_id": 0,
    "product_id": 0,
    "warehouse_id": 0,
    "customer_id": 0,
    "status": "confirmed",
    "is_active": True,
    "is_owner": False,
    "is_reversed": False,
    "tenant_id": None,
}


@pytest.fixture
def mock_db_query(mocker):
    """
    Self-chaining mock for ``db.session.query``.

    Chain methods (``.filter``, ``.filter_by``, ``.order_by``, ``.join``,
    ``.options``, etc.) all return the same mock, so arbitrary SQLAlchemy
    chains never crash.  Use ``.return_value`` to configure call results:

    >>> q = mock_db_query
    >>> q.filter.return_value.first.return_value = (0, 0.0, 0.0)
    >>> q.filter.return_value.scalar.return_value = Decimal("0")
    >>> q.filter.return_value.all.return_value = []
    """
    q = MagicMock(name="db_session_query")
    q.return_value = q  # db.session.query(X) calls q(X) → returns q

    for method in ("filter", "filter_by", "order_by", "join", "options",
                   "group_by", "limit", "offset", "select_from"):
        getattr(q, method).return_value = q

    q.filter.return_value.first.side_effect = cycle([(0, 0.0, 0.0)])
    q.filter.return_value.scalar.side_effect = cycle([Decimal("0")])
    q.filter.return_value.all.return_value = []
    q.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    return q


@pytest.fixture
def model_patch(mocker):
    """
    Factory fixture for patching a model class reference in a target module.

    Usage in a test::

        User = model_patch("routes.owner.User", count=5)
        User.query.filter_by.return_value.count.return_value  # → 5

    The patched model class has safe defaults on column attributes
    (``Decimal("0")``, ``datetime(...)``, etc.) to prevent crashes
    from filter-expression comparisons.  Override via ``cols=``.

    ``.query`` supports:
      * ``.filter_by(..).count()``
      * ``.filter_by(..).join(..).distinct().count()``
      * ``.filter_by(..).order_by(..).limit(N).all()``
      * ``.filter(..).count()``
      * ``.filter(..).order_by(..).limit(N).all()``
    """
    def _patch(target_path, *, count=0, cols=None):
        q = MagicMock(name=f"query_{target_path}")

        fbm = MagicMock(name="filter_by_mock")
        fbm.count.return_value = count
        fbm.join.return_value.distinct.return_value.count.return_value = count
        fbm.order_by.return_value.limit.return_value.all.return_value = []
        fbm.all.return_value = []
        q.filter_by.return_value = fbm

        fm = MagicMock(name="filter_mock")
        fm.count.return_value = count
        fm.order_by.return_value.limit.return_value.all.return_value = []
        fm.all.return_value = []
        q.filter.return_value = fm

        mc = MagicMock(name=f"model_{target_path}")
        mc.query = q

        attrs = dict(_SAFE_COLUMNS)
        if cols:
            attrs.update(cols)
        for attr, val in attrs.items():
            setattr(mc, attr, val)

        mocker.patch(target_path, mc)
        return mc

    return _patch


@pytest.fixture
def mock_db(mocker):
    """Patch ``extensions.db.session`` so add/commit/rollback are no-ops."""
    mock_session = mocker.MagicMock(name="mock_db_session")
    mock_session.get.return_value = None
    mocker.patch("extensions.db.session", mock_session, create=True)
    yield mock_session
    mock_session.get.reset_mock(side_effect=True, return_value=True)


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
    * ``routes.ai.get_ai_access_state`` – returns a fully permissive state so
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
    mocker.patch("routes.ai.get_ai_access_state", return_value={
        "allowed": True,
        "global_enabled": True,
        "tenant_enabled": True,
        "tenant_id": 1,
        "reason": None,
        "is_platform_user": True,
        "ai_level": "execute",
    })
    mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=True)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)

    return user


@pytest.fixture
def mock_ai_service(mocker):
    """
    Patch ``routes.ai.AIService`` static methods so tests never hit a real
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
    recommend_price = mocker.patch("routes.ai.AIService.recommend_price")
    check_stock = mocker.patch("routes.ai.AIService.check_stock_alert")
    analyze_customer = mocker.patch("routes.ai.AIService.analyze_customer_behavior")

    return type("MockAIService", (), {
        "recommend_price": recommend_price,
        "check_stock_alert": check_stock,
        "analyze_customer_behavior": analyze_customer,
    })


@pytest.fixture
def ai_client(app_factory, bypass_ai_access):
    """Test client with the ``ai`` blueprint registered."""
    from routes.ai import ai_bp
    app = app_factory(ai_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Backup / raw DB connection fixture  (pure-logic backup tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_connection(mocker):
    """
    Factory fixture that returns a mock SQLAlchemy ``Connection``.

    Usage::

        conn = mock_db_connection(rows=[(1, "alice")], keys=["id", "name"])
        conn.execute(sa_text("...")).fetchall()   # → [(1, "alice")]
        conn.execute(sa_text("...")).keys()        # → ["id", "name"]
        conn.execute(sa_text("...")).scalar()      # → None

    The returned ``Result`` mock also supports iteration and indexing on rows.
    For multiple sequential calls with different results, use
    ``side_effect`` directly on ``conn.execute.side_effect``.
    """
    def _make(*, rows=None, keys=None, scalar=None):
        rows = rows or []
        keys = keys or []
        conn = mocker.MagicMock(name="mock_conn")
        result = mocker.MagicMock(name="mock_result")
        result.fetchall.return_value = rows
        result.scalar.return_value = scalar
        result.__iter__.return_value = iter(rows)
        result.__getitem__.side_effect = lambda idx: rows[idx] if rows else None

        def keys_side():
            return keys
        result.keys.side_effect = keys_side

        conn.execute.return_value = result
        conn.begin.return_value = mocker.MagicMock()
        return conn

    return _make
