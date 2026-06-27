from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from itertools import cycle
import sys
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, make_response

# Stub heavy optional deps before route package imports (pytest-cov loads routes early).
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
            ANALYTICS_GA_ID="",
            MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        )
        if config_overrides:
            app.config.update(config_overrides)
        app.register_blueprint(blueprint)
        return app
    return _create_app


def _chain_query(**terminals):
    q = MagicMock(name="query_chain")
    q.return_value = q
    for method in (
        "filter", "filter_by", "order_by", "join", "outerjoin", "group_by",
        "limit", "offset", "options", "select_from", "distinct", "having",
    ):
        getattr(q, method).return_value = q
    inner = q.filter.return_value
    inner.first.return_value = terminals.get("first")
    inner.scalar.return_value = terminals.get("scalar", 0)
    inner.all.return_value = terminals.get("all", [])
    inner.count.return_value = terminals.get("count", 0)
    inner.exists.return_value.scalar.return_value = terminals.get("exists", False)
    q.scalar.return_value = terminals.get("scalar", 0)
    q.all.return_value = terminals.get("all", [])
    gb = q.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value
    gb.all.return_value = terminals.get("all", [])
    pag = MagicMock(name="pagination")
    pag.items = terminals.get("all", [])
    pag.page = terminals.get("page", 1)
    pag.per_page = terminals.get("per_page", 20)
    pag.total = terminals.get("count", len(pag.items))
    pag.pages = max(1, (pag.total + pag.per_page - 1) // pag.per_page) if pag.per_page else 1
    pag.has_prev = pag.page > 1
    pag.has_next = pag.page < pag.pages
    pag.prev_num = pag.page - 1
    pag.next_num = pag.page + 1
    q.order_by.return_value.paginate.return_value = pag
    q.paginate.return_value = pag
    return q


def _anon_user():
    user = MagicMock()
    user.is_authenticated = False
    return user


@contextmanager
def unauthenticated_client(client):
    from flask import Response
    login_manager = MagicMock()
    login_manager.unauthorized.return_value = Response("unauthorized", status=401)
    client.application.login_manager = login_manager
    with client.application.app_context():
        with patch("flask_login.utils._get_user", return_value=_anon_user()):
            yield


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
    user.is_owner = False
    role = MagicMock()
    role.slug = "super_admin"
    user.role = role
    return user


@pytest.fixture
def branch_manager_user(mock_user):
    mock_user.branch_id = 2
    mock_user.has_permission.return_value = True
    role = MagicMock()
    role.slug = "manager"
    mock_user.role = role
    mock_user.is_super_admin.return_value = False
    return mock_user


@pytest.fixture
def tenant_owner_user(mock_user):
    mock_user.is_owner = True
    mock_user.tenant_id = 1
    role = MagicMock()
    role.slug = "super_admin"
    mock_user.role = role
    return mock_user


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
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def bypass_admin_auth(mock_user):
    patches = _base_auth_patches(mock_user)
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def bypass_owner_auth(mock_user):
    mock_user.is_owner = True
    patches = _base_auth_patches(mock_user, is_global_owner=True, is_admin_surface=True)
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def bypass_ai_access(mock_user):
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("routes.ai.get_ai_access_state", return_value={
            "allowed": True,
            "global_enabled": True,
            "tenant_enabled": True,
            "tenant_id": 1,
            "reason": None,
            "is_platform_user": True,
            "ai_level": "execute",
        }),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_admin_surface_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("services.logging_core.LoggingCore.log_audit"),
        patch("routes.ai._get_conversation_context", return_value={}),
        patch("routes.ai._set_conversation_context"),
        patch("routes.ai._clear_conversation_context"),
    ]
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def mock_ai_service():
    patch_specs = [
        ("recommend_price", patch("routes.ai.AIService.recommend_price")),
        ("check_stock_alert", patch("routes.ai.AIService.check_stock_alert")),
        ("analyze_customer_behavior", patch("routes.ai.AIService.analyze_customer_behavior")),
        ("chat_response", patch("routes.ai.AIService.chat_response", return_value="mocked chat")),
        ("get_exchange_rate_suggestion", patch("routes.ai.AIService.get_exchange_rate_suggestion", return_value={"rate": 3.67})),
        ("predict_sales_trend", patch("routes.ai.AIService.predict_sales_trend", return_value={"forecast": []})),
        ("analyze_profit_margins", patch("routes.ai.AIService.analyze_profit_margins", return_value={"margins": []})),
        ("detect_sales_patterns", patch("routes.ai.AIService.detect_sales_patterns", return_value={"patterns": []})),
        ("analyze_inventory_health", patch("routes.ai.AIService.analyze_inventory_health", return_value={"health": "ok"})),
        ("deep_business_analysis", patch("routes.ai.AIService.deep_business_analysis", return_value={"analysis": "ok"})),
        ("predict_cash_flow", patch("routes.ai.AIService.predict_cash_flow", return_value={"flow": []})),
        ("predict_customer_churn", patch("routes.ai.AIService.predict_customer_churn", return_value={"churn": []})),
        ("optimize_inventory_levels", patch("routes.ai.AIService.optimize_inventory_levels", return_value={"tips": []})),
        ("generate_business_insights", patch("routes.ai.AIService.generate_business_insights", return_value=[])),
        ("contextual_help", patch("routes.ai.AIService.contextual_help", return_value={"help": "text"})),
        ("smart_pricing_engine", patch("routes.ai.AIService.smart_pricing_engine", return_value={"price": 99})),
        ("ask_genius", patch("routes.ai.AIService.ask_genius", return_value={"answer": "genius"})),
        ("quick_calculate", patch("routes.ai.AIService.quick_calculate", return_value={"success": True, "result": 42})),
        ("understand_with_transformers", patch("routes.ai.AIService.understand_with_transformers", return_value={"intent": "test"})),
        ("get_neural_status", patch("routes.ai.AIService.get_neural_status", return_value={"active": True})),
    ]
    with ExitStack() as stack:
        mocks = {name: stack.enter_context(p) for name, p in patch_specs}
        yield type("MockAIService", (), mocks)


@pytest.fixture
def ai_client(app_factory, bypass_ai_access):
    from routes.ai import ai_bp
    app = app_factory(ai_bp)
    return app.test_client()


@pytest.fixture
def bypass_reports_auth(mock_user):
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("utils.tenanting.require_report_tenant_id"),
        patch("utils.decorators.report_branch_scope_id", return_value=None),
        patch("routes.reports.render_template", return_value="ok"),
        patch("routes.reports.tenant_query", side_effect=lambda model: _chain_query(all=[])),
        patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query(scalar=0, exists=False)),
        patch("routes.reports.get_confirmed_sale_paid_aed", return_value=Decimal("0")),
        patch("routes.reports.get_confirmed_supplier_paid_aed", return_value=Decimal("0")),
    ]
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def reports_client(app_factory, bypass_reports_auth):
    from routes.reports import reports_bp
    app = app_factory(reports_bp)
    return app.test_client()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.id = 1
    store.store_slug = "demo-store"
    store.tenant_id = 1
    store.name = "Demo Store"
    store.is_active = True
    store.is_enabled = True
    store.min_order_amount = Decimal("0")
    store.phone = "+971500000000"
    store.whatsapp = "+971500000000"
    store.brand_color_primary = "#1B7A4E"
    store.brand_color_secondary = "#CE1126"
    return store


@pytest.fixture
def bypass_shop_auth(mock_store):
    tenant = MagicMock()
    tenant.brand_color_primary = "#1B7A4E"
    tenant.brand_color_secondary = "#CE1126"
    tenant.is_active = True
    tenant.is_suspended = False
    mock_db_session = MagicMock()
    mock_db_session.get.return_value = tenant
    patches = [
        patch("routes.shop.StoreService.get_store_by_slug", return_value=mock_store),
        patch("routes.shop.StoreService.stores_globally_enabled", return_value=True),
        patch("routes.shop.StoreService.is_platform_locked", return_value=False),
        patch("routes.shop.StoreService.get_cart", return_value={}),
        patch("routes.shop.StoreService.save_cart"),
        patch("routes.shop.StoreService.cart_totals", return_value={
            "lines": [], "subtotal": Decimal("0"), "total": Decimal("0"), "tax": Decimal("0"),
        }),
        patch("routes.shop.StoreService.get_public_catalog", return_value={
            "items": [], "total": 0, "pages": 1, "page": 1,
        }),
        patch("routes.shop.StoreService.online_stock_map", return_value={}),
        patch("routes.shop.StoreService.get_recently_viewed_products", return_value=[]),
        patch("routes.shop.StoreService.get_product_variants", return_value=[]),
        patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None),
        patch("routes.shop.ShopCustomerAuthService.login"),
        patch("routes.shop.ShopCustomerAuthService.logout"),
        patch("routes.shop.db.session", mock_db_session),
        patch("routes.shop.render_template", return_value="ok"),
        patch("routes.shop.Product.query", new_callable=MagicMock),
        patch("routes.shop.ProductCategory.query", new_callable=MagicMock),
        patch("routes.shop.ShopReview.query", new_callable=MagicMock),
        patch("routes.shop.Sale.query", new_callable=MagicMock),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("routes.shop.shop_lang", return_value="ar"),
        patch("routes.shop.t", side_effect=lambda k, lang=None: k),
    ]
    for p in patches:
        p.start()
    yield mock_store
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def shop_client(app_factory, bypass_shop_auth):
    from routes.shop import shop_bp
    app = app_factory(shop_bp)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["shop_lang_demo-store"] = "ar"
        yield client

@pytest.fixture
def bypass_customers_auth(mock_user):
    customer = MagicMock()
    customer.id = 1
    customer.name = "Test Customer"
    customer.phone = "0500000000"
    customer.email = "c@test.com"
    customer.customer_type = "regular"
    customer.customer_classification = "regular"
    customer.is_active = True
    customer.tenant_id = 1
    customer.balance = Decimal("0")
    customer.created_at = MagicMock(strftime=lambda fmt: "2025-01-01")
    customer.name_ar = ""
    customer.preferred_currency = "AED"
    customer.to_dict.return_value = {"id": 1, "name": "Test Customer"}
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_admin_surface_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("utils.decorators.branch_scope_id", return_value=None),
        patch("utils.decorators.report_branch_scope_id", return_value=None),
        patch("routes.customers.render_template", return_value="ok"),
        patch("routes.customers.tenant_query", side_effect=lambda model: _chain_query(all=[customer])),
        patch("routes.customers.tenant_get_or_404", return_value=customer),
        patch("routes.customers.assert_tenant_record"),
        patch("routes.customers.PaymentService.get_customer_balance_aed", return_value=Decimal("0")),
        patch("routes.customers.PaymentService.get_customer_balance_scoped", return_value=Decimal("0")),
        patch("routes.customers.should_show_all_branch_columns", return_value=False),
        patch("routes.customers.LoggingCore.log_audit"),
        patch("routes.customers._customer_in_scope", return_value=True),
        patch("routes.customers._get_unpaid_sales", return_value=[]),
        patch("routes.customers.Sale"),
        patch("routes.customers.db"),
    ]
    for p in patches:
        p.start()
    from routes.customers import Sale as SaleMod, db as cust_db
    SaleMod.query.filter_by.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    cust_db.session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    cust_db.session.query.return_value.filter.return_value.all.return_value = []
    yield mock_user, customer
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def customers_client(app_factory, bypass_customers_auth):
    from routes.customers import customers_bp
    app = app_factory(customers_bp)
    return app.test_client()

