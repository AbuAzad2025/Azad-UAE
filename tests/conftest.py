"""
Pytest configuration and shared fixtures for the Azad UAE ERP test suite.
"""
import os
import shutil
import sys
import pytest
from sqlalchemy import text as sa_text

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)


def pytest_configure(config):
    """Clean up previous pytest temp dir to prevent PermissionError at exit on Windows."""
    temp_dir = os.path.join(PROJECT_ROOT, "tests", ".pytest-temp")
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae")
os.environ.setdefault("CACHE_TYPE", "null")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "memory://")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 3,
        "max_overflow": 2,
        "pool_pre_ping": True,
        "pool_timeout": 10,
    }
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "null"
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "memory://"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_DEFAULT = "10000 per day;1000 per hour"
    MAIL_USERNAME = None
    MAIL_PASSWORD = None
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ENABLE_MWAC = True
    ENABLE_DYNAMIC_GL_MAPPING = False
    ENABLE_LANDED_COST_CAPITALIZATION = True
    ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK = False
    ENABLE_ADVANCED_RECONCILIATION = True
    ENABLE_TREASURY = True
    ENABLE_LOCALIZATION_FRAMEWORK = False
    ENABLE_LOAD_TESTING = False
    ENABLE_FULL_REGRESSION = False
    DEFAULT_CURRENCY = "AED"
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False
    SESSION_COOKIE_NAME = "test_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = False
    REMEMBER_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_BLOCK_DURATION = 900
    CORS_ORIGINS = ["http://localhost:5000"]
    CORS_SUPPORTS_CREDENTIALS = True
    COMPRESS_MIMETYPES = ['text/html', 'text/css', 'text/xml', 'text/plain',
                          'application/json', 'application/javascript']
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    COMPRESS_ALGORITHM = 'gzip'
    APP_ENV = "testing"
    DEBUG = True
    HOST = "127.0.0.1"
    PORT = 5000


@pytest.fixture(scope="session")
def app():
    """Create and configure the Flask app for testing against real PostgreSQL."""
    from app import create_app
    from extensions import db
    from services.logging_core import LoggingCore

    original_log_error = LoggingCore.log_error
    original_log_frontend = LoggingCore.log_frontend_error
    LoggingCore.log_error = lambda *args, **kwargs: None
    LoggingCore.log_frontend_error = lambda *args, **kwargs: None

    app = create_app(config_class=TestConfig)

    with app.app_context():
        yield app
        db.session.remove()

    LoggingCore.log_error = original_log_error
    LoggingCore.log_frontend_error = original_log_frontend


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    from extensions import db
    with app.app_context():
        db.session.expire_all()
        yield db.session
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def sample_tenant(db_session):
    import uuid
    from models import Tenant
    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Test Company {unique}",
        name_ar="شركة تجربة",
        slug=f"test-company-{unique}",
        email=f"test-{unique}@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def sample_permissions(db_session):
    """Create all commonly needed permissions for tests (idempotent)."""
    from models import Permission
    codes = [
        "admin", "view_reports", "view_ledger", "manage_sales", "manage_purchases",
        "manage_expenses", "manage_payroll", "manage_payments", "manage_products",
        "manage_customers", "manage_suppliers", "manage_inventory", "manage_warehouse",
    ]
    existing = {p.code: p for p in Permission.query.all()}
    perms = []
    for code in codes:
        p = existing.get(code)
        if p is None:
            p = Permission(code=code, name=code, name_ar=code, category="test")
            db_session.add(p)
        perms.append(p)
    db_session.commit()
    return perms


@pytest.fixture
def sample_role(db_session, sample_permissions):
    import uuid
    from models import Role
    unique = str(uuid.uuid4())[:8]
    role = Role(
        name=f"Manager {unique}",
        slug=f"manager-{unique}",
        is_active=True,
    )
    for p in sample_permissions:
        role.permissions.append(p)
    db_session.add(role)
    db_session.commit()
    return role


@pytest.fixture
def sample_branch(db_session, sample_tenant):
    """Creates a sample branch for a tenant."""
    from models import Branch
    import uuid
    unique = str(uuid.uuid4())[:8]
    branch = Branch(
        tenant_id=sample_tenant.id,
        name=f"Main Branch {unique}",
        code=f"BR{unique[:4].upper()}",
        is_active=True,
        is_main=True,
    )
    db_session.add(branch)
    db_session.commit()
    return branch


@pytest.fixture
def sample_user(db_session, sample_tenant, sample_role, sample_branch):
    import uuid
    from models import User
    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"testuser-{unique}",
        email=f"user-{unique}@example.com",
        full_name="Test User",
        tenant_id=sample_tenant.id,
        role_id=sample_role.id,
        branch_id=sample_branch.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_owner(db_session):
    import uuid
    from models import Tenant, Role, User
    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Owner Co {unique}",
        name_ar="شركة المالك",
        slug=f"owner-co-{unique}",
        email=f"owner-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()
    role = Role(name="Owner", slug="owner", is_active=True)
    db_session.add(role)
    db_session.commit()
    user = User(
        username=f"owner-{unique}",
        email=f"owner-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=tenant.id,
        role_id=role.id,
        is_active=True,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_client(client, sample_user):
    """A logged-in test client for tenant users via actual login."""
    from flask import session
    with client:
        resp = client.post('/auth/login', data={
            'username': sample_user.username,
            'password': 'password123',
        }, follow_redirects=True)
    return client


@pytest.fixture
def owner_client(client, sample_owner):
    """A logged-in test client for platform owner via actual login."""
    with client:
        resp = client.post('/auth/login', data={
            'username': sample_owner.username,
            'password': 'password123',
        }, follow_redirects=True)
    return client


@pytest.fixture
def sample_supplier(db_session, sample_tenant):
    from models import Supplier
    supplier = Supplier(
        tenant_id=sample_tenant.id,
        name="Test Supplier",
        email="supplier@test.com",
        phone="0555000000",
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


@pytest.fixture
def sample_customer(db_session, sample_tenant):
    from models import Customer
    customer = Customer(
        tenant_id=sample_tenant.id,
        name="Test Customer",
        email="customer@test.com",
        phone="0555000001",
    )
    db_session.add(customer)
    db_session.commit()
    return customer


@pytest.fixture
def sample_purchase(db_session, sample_tenant, sample_supplier, sample_user):
    from decimal import Decimal
    from datetime import datetime, timezone
    from models import Purchase
    p = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number="PUR-TEST-001",
        supplier_id=sample_supplier.id,
        supplier_name="Test Supplier",
        purchase_date=datetime.now(timezone.utc),
        user_id=sample_user.id,
        subtotal=Decimal("100.000"),
        total_amount=Decimal("105.000"),
        amount=Decimal("105.000"),
        amount_aed=Decimal("105.000"),
        currency="AED",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def sample_expense_category(db_session, sample_tenant):
    from models import ExpenseCategory
    cat = ExpenseCategory(tenant_id=sample_tenant.id, name="Utilities")
    db_session.add(cat)
    db_session.commit()
    return cat


@pytest.fixture
def sample_expense(db_session, sample_tenant, sample_expense_category, sample_user):
    from datetime import datetime, timezone
    from decimal import Decimal
    from models import Expense
    e = Expense(
        tenant_id=sample_tenant.id,
        expense_number="EXP-TEST-001",
        category_id=sample_expense_category.id,
        description="Test expense",
        expense_date=datetime.now(timezone.utc),
        user_id=sample_user.id,
        amount=Decimal("500.000"),
        amount_aed=Decimal("500.000"),
        payment_method="cash",
    )
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def sample_employee(db_session, sample_tenant):
    from models import Employee
    emp = Employee(
        tenant_id=sample_tenant.id,
        name="Test Employee",
        basic_salary=5000,
    )
    db_session.add(emp)
    db_session.commit()
    return emp


@pytest.fixture
def sample_payroll_transaction(db_session, sample_tenant, sample_employee):
    from datetime import datetime, timezone
    from decimal import Decimal
    from models import PayrollTransaction
    pt = PayrollTransaction(
        tenant_id=sample_tenant.id,
        employee_id=sample_employee.id,
        month=6,
        year=2026,
        basic_amount=Decimal("5000.00"),
        net_salary=Decimal("5000.00"),
        status="paid",
    )
    db_session.add(pt)
    db_session.commit()
    return pt


@pytest.fixture
def sample_cheque(db_session, sample_tenant):
    from datetime import date
    from decimal import Decimal
    from models import Cheque
    ch = Cheque(
        tenant_id=sample_tenant.id,
        cheque_number="CHQ-TEST-001",
        cheque_bank_number="BNK-001",
        cheque_type="incoming",
        bank_name="Test Bank",
        amount=Decimal("10000.00"),
        amount_aed=Decimal("10000.00"),
        issue_date=date.today(),
        due_date=date.today(),
    )
    db_session.add(ch)
    db_session.commit()
    return ch


@pytest.fixture
def sample_sale(db_session, sample_tenant, sample_customer, sample_user):
    from datetime import datetime, timezone
    from decimal import Decimal
    from models import Sale
    s = Sale(
        tenant_id=sample_tenant.id,
        sale_number="SAL-TEST-001",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(timezone.utc),
        subtotal=Decimal("200.000"),
        total_amount=Decimal("210.000"),
        amount=Decimal("210.000"),
        amount_aed=Decimal("210.000"),
        paid_amount=Decimal("0"),
        balance_due=Decimal("210.000"),
        currency="AED",
    )
    db_session.add(s)
    db_session.commit()
    return s


@pytest.fixture
def sample_warehouse(db_session, sample_tenant, sample_branch):
    from models import Warehouse
    w = Warehouse(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name="Main Warehouse",
        name_ar="المستودع الرئيسي",
        is_active=True,
    )
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def sample_product(db_session, sample_tenant, sample_warehouse):
    from decimal import Decimal
    from models import Product
    p = Product(
        tenant_id=sample_tenant.id,
        name="Test Product",
        sku="SKU-TEST-001",
        cost_price=Decimal("50.000"),
        regular_price=Decimal("100.000"),
        current_stock=Decimal("100.000"),
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def sample_product_with_stock(db_session, sample_tenant, sample_warehouse):
    """Create a product with real stock via StockService."""
    from decimal import Decimal
    from models import Product, ProductWarehouseStock
    from services.stock_service import StockService
    p = Product(
        tenant_id=sample_tenant.id,
        name="Stocked Product",
        sku="SKU-STOCK-001",
        cost_price=Decimal("50.000"),
        regular_price=Decimal("100.000"),
        current_stock=Decimal("0"),
    )
    db_session.add(p)
    db_session.commit()
    StockService.add_stock(p.id, 100, warehouse_id=sample_warehouse.id)
    db_session.refresh(p)
    return p


@pytest.fixture
def sample_gl_accounts(db_session, sample_tenant):
    """Ensure core chart of accounts exists for the tenant."""
    from services.gl_service import GLService
    GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
    db_session.commit()
    return sample_tenant


@pytest.fixture
def sample_currency_aed(db_session, sample_tenant):
    """Ensure AED currency exists."""
    from models import Currency
    c = Currency.query.filter_by(code="AED").first()
    if not c:
        c = Currency(code="AED", name="UAE Dirham", name_ar="درهم إماراتي", symbol="د.إ", rate_to_base=1)
        db_session.add(c)
        db_session.commit()
    return c


@pytest.fixture
def logged_in_client(client, sample_user):
    """A test client authenticated as sample_user via real login."""
    client.post('/auth/login', data={'username': sample_user.username, 'password': 'password123'}, follow_redirects=True)
    return client
