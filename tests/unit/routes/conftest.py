import warnings
from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
import sys
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask

warnings.filterwarnings(
    "ignore", message="coroutine 'AsyncMockMixin._execute_mock_call' was never awaited"
)

for _mod in ("numpy", "pandas"):
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
    if not config.pluginmanager.hasplugin("_cov"):
        return
    import importlib
    import sqlalchemy.orm.dependency as _dep

    if not hasattr(_dep, "_direction_to_processor"):
        importlib.reload(_dep)


# ─── REAL AUTHENTICATION HELPERS ───
def _create_test_user(
    db_session,
    tenant_id=1,
    username="testuser",
    email="test@example.com",
    is_owner=False,
    is_admin=True,
    permissions=None,
):
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

    role = (
        db_session.query(Role)
        .filter_by(slug="super_admin" if is_admin else "manager")
        .first()
    )
    if not role:
        role = Role(
            name="Super Admin" if is_admin else "Manager",
            slug="super_admin" if is_admin else "manager",
            is_active=True,
        )
        db_session.add(role)
        db_session.flush()

    # Default permissions for test users
    default_perms = [
        "manage_customers",
        "manage_sales",
        "manage_purchases",
        "manage_inventory",
        "manage_payments",
        "manage_expenses",
        "view_reports",
        "manage_products",
        "manage_warehouse",
        "manage_suppliers",
        "manage_branches",
        "admin",
    ]
    perm_codes = permissions if permissions else default_perms

    for perm_code in perm_codes:
        perm = db_session.query(Permission).filter_by(code=perm_code).first()
        if not perm:
            perm = Permission(
                code=perm_code, name=perm_code, name_ar=perm_code, category="test"
            )
            db_session.add(perm)
            db_session.flush()
        # Check if permission is already assigned to role
        if perm not in role.permissions:
            role.permissions.append(perm)

    branch = (
        db_session.query(Branch).filter_by(tenant_id=tenant_id, is_main=True).first()
    )
    if not branch:
        branch = Branch(
            tenant_id=tenant_id,
            name="Main Branch",
            code="MAIN",
            is_active=True,
            is_main=True,
        )
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
    return client.post(
        "/auth/login",
        data={
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )


def logout_user_via_client(client):
    return client.get("/auth/logout", follow_redirects=True)


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
        patch(
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
        ),
        patch(
            "routes.ai_routes.chat.get_ai_access_state",
            return_value={
                "allowed": True,
                "global_enabled": True,
                "tenant_enabled": True,
                "tenant_id": 1,
                "reason": None,
                "is_platform_user": True,
                "ai_level": "execute",
            },
        ),
        patch(
            "routes.ai_routes.shared.get_ai_access_state",
            return_value={
                "allowed": True,
                "global_enabled": True,
                "tenant_enabled": True,
                "tenant_id": 1,
                "reason": None,
                "is_platform_user": True,
                "ai_level": "execute",
            },
        ),
        patch(
            "routes.ai_routes.assistant.get_ai_access_state",
            return_value={
                "allowed": True,
                "global_enabled": True,
                "tenant_enabled": True,
                "tenant_id": 1,
                "reason": None,
                "is_platform_user": True,
                "ai_level": "execute",
            },
        ),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_admin_surface_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("services.logging_core.LoggingCore.log_audit"),
        patch("routes.ai_routes._get_conversation_context", return_value={}),
        patch("utils.context_managers._set_conversation_context"),
        patch("routes.ai_routes._clear_conversation_context"),
        patch("routes.ai_routes.shared._get_conversation_context", return_value={}),
        patch("routes.ai_routes.shared._set_conversation_context"),
        patch("routes.ai_routes.shared._clear_conversation_context"),
    ]
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


# ─── TEST DATA FACTORY ───
class TestFactory:
    """Helper factory for creating test data with proper tenant isolation and required fields."""

    def __init__(self, db_session, user):
        self.db_session = db_session
        self.user = user

    @staticmethod
    def _set_tenant_id_on_obj(obj, tenant_id):
        """Set tenant_id on an object, bypassing tenant isolation guard."""
        if hasattr(obj, "tenant_id"):
            obj.tenant_id = tenant_id
        return obj

    def create_customer(self, name="Test Customer", tenant_id=None, **kwargs):
        """Create a Customer with proper tenant isolation.

        Automatically injects tenant_id from the current user and removes
        any branch_id (which doesn't exist on the Customer model).

        Args:
            name: Customer name
            tenant_id: Optional tenant_id override for cross-tenant testing
            **kwargs: Additional Customer fields
        """
        from models import Customer, Tenant
        from flask import g

        kwargs.pop("branch_id", None)  # Customer model doesn't have branch_id
        actual_tenant_id = tenant_id if tenant_id is not None else self.user.tenant_id

        # Ensure tenant exists for cross-tenant tests
        if tenant_id is not None and tenant_id != self.user.tenant_id:
            # Create the foreign tenant if it doesn't exist
            existing_tenant = self.db_session.get(Tenant, tenant_id)
            if not existing_tenant:
                existing_tenant = Tenant(
                    id=tenant_id,
                    name=f"Test Tenant {tenant_id}",
                    name_ar="مستأجر اختبار",
                    slug=f"test-tenant-{tenant_id}",
                    email=f"tenant{tenant_id}@example.com",
                    country="AE",
                    subscription_plan="basic",
                    default_currency="AED",
                    base_currency="AED",
                    is_active=True,
                )
                self.db_session.add(existing_tenant)
                self.db_session.flush()
            g.skip_tenant_scope = True

        customer = Customer(tenant_id=actual_tenant_id, name=name, **kwargs)
        self.db_session.add(customer)
        self.db_session.commit()
        g.skip_tenant_scope = False
        return customer

    def create_sale(self, customer, total_amount=100.00, **kwargs):
        """Create a Sale with proper tenant isolation and required fields.

        Automatically injects tenant_id from the current user and seller_id
        from the current user (required field on Sale model).
        """
        from models import Sale

        sale = Sale(
            tenant_id=self.user.tenant_id,
            customer_id=customer.id,
            sale_number=kwargs.pop(
                "sale_number", f"S-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            ),
            sale_date=kwargs.pop("sale_date", datetime.now()),
            subtotal=kwargs.pop("subtotal", total_amount),
            total_amount=total_amount,
            amount=total_amount,
            amount_aed=total_amount,
            currency=kwargs.pop("currency", "AED"),
            paid_amount=kwargs.pop("paid_amount", 0),
            balance_due=kwargs.pop("balance_due", total_amount),
            exchange_rate=kwargs.pop("exchange_rate", 1),
            payment_status=kwargs.pop("payment_status", "unpaid"),
            status=kwargs.pop("status", "confirmed"),
            source=kwargs.pop("source", "internal"),
            notes=kwargs.pop("notes", ""),
            seller_id=self.user.id,  # Required field on Sale model
        )
        self.db_session.add(sale)
        self.db_session.commit()
        return sale

    def create_payment(self, customer, sale=None, amount=50.00, **kwargs):
        """Create a Payment with proper tenant isolation."""
        from models import Payment

        payment = Payment(
            tenant_id=self.user.tenant_id,
            customer_id=customer.id,
            sale_id=sale.id if sale else None,
            payment_number=kwargs.pop(
                "payment_number", f"P-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            ),
            payment_date=kwargs.pop("payment_date", datetime.now()),
            amount_aed=amount,
            amount=amount,
            currency=kwargs.pop("currency", "AED"),
            exchange_rate=kwargs.pop("exchange_rate", 1),
            reference_number=kwargs.pop(
                "reference_number", f"REF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            ),
            payment_method=kwargs.pop("payment_method", "cash"),
            payment_confirmed=kwargs.pop("payment_confirmed", True),
            direction=kwargs.pop("direction", "incoming"),
            payment_type=kwargs.pop("payment_type", "cash"),
        )
        self.db_session.add(payment)
        self.db_session.commit()
        return payment

    def create_receipt(self, customer, amount=25.00, **kwargs):
        """Create a Receipt with proper tenant isolation."""
        from models import Receipt

        receipt = Receipt(
            tenant_id=self.user.tenant_id,
            customer_id=customer.id,
            receipt_number=kwargs.pop(
                "receipt_number", f"RCV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            ),
            receipt_date=kwargs.pop("receipt_date", datetime.now()),
            amount_aed=amount,
            amount=amount,
            currency=kwargs.pop("currency", "AED"),
            exchange_rate=kwargs.pop("exchange_rate", 1),
            payment_method=kwargs.pop("payment_method", "cash"),
            payment_confirmed=kwargs.pop("payment_confirmed", True),
            notes=kwargs.pop("notes", ""),
        )
        self.db_session.add(receipt)
        self.db_session.commit()
        return receipt


@pytest.fixture
def test_factory(db_session, sample_user):
    """Provides a test data factory bound to the current authenticated user.

    Usage:
        def test_something(test_factory):
            customer = test_factory.create_customer(name="Test Customer")
            sale = test_factory.create_sale(customer, total_amount=100.00)
    """
    return TestFactory(db_session, sample_user)


# ─── CHAIN QUERY HELPERS ───
def _chain_query(**terminals):
    q = MagicMock(name="query_chain")
    q.return_value = q
    for method in (
        "filter",
        "filter_by",
        "order_by",
        "join",
        "outerjoin",
        "group_by",
        "limit",
        "offset",
    ):
        getattr(q, method).return_value = q
    inner = q.filter.return_value
    inner.first.return_value = terminals.get("first")
    inner.scalar.return_value = terminals.get("scalar", 0)
    inner.all.return_value = terminals.get("all", [])
    inner.count.return_value = terminals.get("count", 0)
    inner.exists.return_value.scalar.return_value = terminals.get("exists", True)
    q.scalar.return_value = terminals.get("scalar", 0)
    q.all.return_value = terminals.get("all", [])
    pag = MagicMock(name="pagination")
    pag.items = terminals.get("all", [])
    pag.page = 1
    pag.per_page = 20
    pag.total = len(pag.items)
    pag.pages = 1
    q.order_by.return_value.paginate.return_value = pag
    q.paginate.return_value = pag
    return q


def _stub_query(**terminals):
    q = MagicMock(name="query_chain")
    q.return_value = q
    for method in (
        "filter",
        "filter_by",
        "order_by",
        "join",
        "outerjoin",
        "group_by",
        "limit",
        "offset",
        "options",
        "select_from",
        "distinct",
        "having",
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


@pytest.fixture
def mock_ai_service():
    patch_specs = [
        ("recommend_price", patch("routes.ai_routes.AIService.recommend_price")),
        ("check_stock_alert", patch("routes.ai_routes.AIService.check_stock_alert")),
        (
            "analyze_customer_behavior",
            patch("routes.ai_routes.AIService.analyze_customer_behavior"),
        ),
        (
            "chat_response",
            patch(
                "routes.ai_routes.AIService.chat_response", return_value="mocked chat"
            ),
        ),
        (
            "get_exchange_rate_suggestion",
            patch(
                "routes.ai_routes.AIService.get_exchange_rate_suggestion",
                return_value={"rate": 3.67},
            ),
        ),
        (
            "predict_sales_trend",
            patch(
                "routes.ai_routes.AIService.predict_sales_trend",
                return_value={"forecast": []},
            ),
        ),
        (
            "analyze_profit_margins",
            patch(
                "routes.ai_routes.AIService.analyze_profit_margins",
                return_value={"margins": []},
            ),
        ),
        (
            "detect_sales_patterns",
            patch(
                "routes.ai_routes.AIService.detect_sales_patterns",
                return_value={"patterns": []},
            ),
        ),
        (
            "analyze_inventory_health",
            patch(
                "routes.ai_routes.AIService.analyze_inventory_health",
                return_value={"health": "ok"},
            ),
        ),
        (
            "deep_business_analysis",
            patch(
                "routes.ai_routes.AIService.deep_business_analysis",
                return_value={"analysis": "ok"},
            ),
        ),
        (
            "predict_cash_flow",
            patch(
                "routes.ai_routes.AIService.predict_cash_flow",
                return_value={"flow": []},
            ),
        ),
        (
            "predict_customer_churn",
            patch(
                "routes.ai_routes.AIService.predict_customer_churn",
                return_value={"churn": []},
            ),
        ),
        (
            "optimize_inventory_levels",
            patch(
                "routes.ai_routes.AIService.optimize_inventory_levels",
                return_value={"tips": []},
            ),
        ),
        (
            "generate_business_insights",
            patch(
                "routes.ai_routes.AIService.generate_business_insights", return_value=[]
            ),
        ),
        (
            "contextual_help",
            patch(
                "routes.ai_routes.AIService.contextual_help",
                return_value={"help": "text"},
            ),
        ),
        (
            "smart_pricing_engine",
            patch(
                "routes.ai_routes.AIService.smart_pricing_engine",
                return_value={"price": 99},
            ),
        ),
        (
            "ask_genius",
            patch(
                "routes.ai_routes.AIService.ask_genius",
                return_value={"answer": "genius"},
            ),
        ),
        (
            "quick_calculate",
            patch(
                "routes.ai_routes.AIService.quick_calculate",
                return_value={"success": True, "result": 42},
            ),
        ),
        (
            "understand_with_transformers",
            patch(
                "routes.ai_routes.AIService.understand_with_transformers",
                return_value={"intent": "test"},
            ),
        ),
        (
            "get_neural_status",
            patch(
                "routes.ai_routes.AIService.get_neural_status",
                return_value={"active": True},
            ),
        ),
    ]
    with ExitStack() as stack:
        mocks = {name: stack.enter_context(p) for name, p in patch_specs}
        yield type("MockAIService", (), mocks)


@pytest.fixture
def advanced_ledger_client(app_factory, bypass_admin_auth):
    from routes.advanced_ledger import advanced_ledger_bp

    app = app_factory(advanced_ledger_bp)
    return app.test_client()


@pytest.fixture
def ai_client(app_factory, bypass_ai_access):
    from routes.ai_routes import ai_bp

    app = app_factory(ai_bp)
    stub = MagicMock(name="query_chain")
    stub.return_value = stub
    for method in (
        "filter",
        "filter_by",
        "order_by",
        "join",
        "outerjoin",
        "group_by",
        "limit",
        "offset",
        "options",
        "select_from",
        "distinct",
        "having",
    ):
        getattr(stub, method).return_value = stub
    stub.filter.return_value.scalar.return_value = 0
    stub.filter.return_value.all.return_value = []
    stub.filter.return_value.exists.return_value.scalar.return_value = False
    stub.all.return_value = []
    with (
        patch("routes.ai_routes.db.session.query", return_value=stub),
        patch("routes.ai_routes.db.session.get", return_value=None),
        patch("routes.ai_routes.chat.db.session.query", return_value=stub),
        patch("routes.ai_routes.chat.db.session.get", return_value=None),
        patch("routes.ai_routes.chat.db.session.add"),
        patch("routes.ai_routes.chat.db.session.commit"),
    ):
        yield app.test_client()


@pytest.fixture
def bypass_reports_auth(mock_user):
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("utils.tenanting.require_report_tenant_id"),
        patch("utils.decorators.report_branch_scope_id", return_value=None),
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
    with (
        patch("routes.reports.render_template", return_value="ok"),
        patch("routes.reports.db.session.query", return_value=_stub_query()),
        patch("routes.reports.tenant_query", return_value=_stub_query()),
    ):
        yield app.test_client()


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
    patches = [
        patch("routes.shop.StoreService.get_store_by_slug", return_value=mock_store),
        patch("routes.shop.StoreService.stores_globally_enabled", return_value=True),
        patch("routes.shop.StoreService.is_platform_locked", return_value=False),
        patch("routes.shop.StoreService.get_cart", return_value={}),
        patch("routes.shop.StoreService.save_cart"),
        patch(
            "routes.shop.StoreService.cart_totals",
            return_value={
                "lines": [],
                "subtotal": Decimal("0"),
                "total": Decimal("0"),
                "tax": Decimal("0"),
            },
        ),
        patch(
            "routes.shop.StoreService.get_public_catalog",
            return_value={
                "items": [],
                "total": 0,
                "pages": 1,
                "page": 1,
            },
        ),
        patch("routes.shop.StoreService.online_stock_map", return_value={}),
        patch("routes.shop.StoreService.get_recently_viewed_products", return_value=[]),
        patch("routes.shop.StoreService.get_product_variants", return_value=[]),
        patch(
            "routes.shop.ShopCustomerAuthService.get_logged_in_account",
            return_value=None,
        ),
        patch("routes.shop.ShopCustomerAuthService.login"),
        patch("routes.shop.ShopCustomerAuthService.logout"),
        patch("routes.shop.render_template", return_value="ok"),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("routes.shop.shop_lang", return_value="ar"),
        patch("routes.shop.t", side_effect=lambda k, lang=None: k),
        patch("routes.shop.db.session.get", return_value=tenant),
        patch("routes.shop.db.session.add"),
        patch("routes.shop.db.session.commit"),
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
def vault_owner_client(app_factory, bypass_owner_auth):
    from routes.payment_vault import payment_vault_bp

    app = app_factory(payment_vault_bp)
    return app.test_client()


@pytest.fixture
def bypass_customers_auth(mock_user):
    patches = [
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_global_owner_user", return_value=True),
        patch("utils.decorators.is_admin_surface_user", return_value=True),
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
        patch("utils.decorators.branch_scope_id", return_value=None),
        patch("utils.decorators.report_branch_scope_id", return_value=None),
        patch("routes.customers.LoggingCore.log_audit"),
        patch("routes.customers.render_template", return_value="ok"),
        patch("routes.customers._get_unpaid_sales", return_value=[]),
        patch("routes.customers._customer_in_scope", return_value=True),
        patch("routes.customers._get_customer_balance", return_value=Decimal("0")),
        patch("routes.customers._scoped_customer_query"),
        patch("routes.customers.tenant_get_or_404"),
    ]
    for p in patches:
        p.start()
    yield mock_user
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def customers_client(app_factory, bypass_customers_auth):
    from routes.customers import customers_bp

    app = app_factory(customers_bp)
    return app.test_client()


@pytest.fixture
def app_factory():
    def _create_app(*blueprints, config_overrides=None):
        import sys
        import os

        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        sys.path.insert(0, project_root)
        from tests.conftest import TestConfig
        from extensions import db

        app = Flask(__name__, template_folder=os.path.join(project_root, "templates"))
        app.config.from_object(TestConfig)
        if config_overrides:
            app.config.update(config_overrides)
        db.init_app(app)

        from extensions import babel, get_locale

        babel.init_app(app, locale_selector=get_locale)

        from utils.i18n import t

        app.jinja_env.globals["t"] = t
        app.jinja_env.globals["csrf_token"] = lambda: ""
        from flask_login import current_user

        app.jinja_env.globals["current_user"] = current_user

        from routes.main import main_bp

        for bp in blueprints:
            if isinstance(bp, dict):
                app.config.update(bp)
                continue
            app.register_blueprint(bp)
        if "main" not in app.blueprints:
            app.register_blueprint(main_bp)
        return app

    return _create_app
