"""
Pytest configuration and shared fixtures for the Azad UAE ERP test suite.
"""
import os
import sys
import pytest
from sqlalchemy import text as sa_text

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CACHE_TYPE", "null")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "memory://")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")


class TestConfig:
    """Test configuration that works with SQLite or PostgreSQL (CI)."""
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite-only connect arg; leave empty for PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"connect_args": {"check_same_thread": False}}
        if os.environ.get("DATABASE_URL", "sqlite").startswith("sqlite")
        else {}
    )
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
    ENABLE_DYNAMIC_GL_MAPPING = True
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
    """Create and configure the Flask app for testing."""
    from app import create_app
    from extensions import db
    import services.error_audit_service as eas

    # Disable error audit logging during tests to avoid DB locked errors
    original_log = eas.ErrorAuditService.log
    original_log_exception = eas.ErrorAuditService.log_exception
    original_log_frontend = eas.ErrorAuditService.log_frontend
    eas.ErrorAuditService.log = lambda *args, **kwargs: None
    eas.ErrorAuditService.log_exception = lambda *args, **kwargs: None
    eas.ErrorAuditService.log_frontend = lambda *args, **kwargs: None

    app = create_app(config_class=TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        # Disable FK constraints before drop to avoid SAWarning on SQLite FK cycles
        if str(db.engine.url).startswith("sqlite"):
            with db.engine.connect() as conn:
                conn.execute(sa_text("PRAGMA foreign_keys=OFF"))
        db.drop_all()

    # Restore original functions
    eas.ErrorAuditService.log = original_log
    eas.ErrorAuditService.log_exception = original_log_exception
    eas.ErrorAuditService.log_frontend = original_log_frontend


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Yield a database session inside the app context."""
    from extensions import db
    with app.app_context():
        yield db.session


@pytest.fixture
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()


@pytest.fixture
def sample_tenant(db_session):
    """Create a sample tenant for tests."""
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
def sample_role(db_session):
    """Create a sample role for tests."""
    import uuid
    from models import Role
    unique = str(uuid.uuid4())[:8]
    role = Role(
        name=f"Manager {unique}",
        slug=f"manager-{unique}",
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return role


@pytest.fixture
def sample_user(db_session, sample_tenant, sample_role):
    """Create a sample user for tests."""
    import uuid
    from models import User
    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"testuser-{unique}",
        email=f"user-{unique}@example.com",
        full_name="Test User",
        tenant_id=sample_tenant.id,
        role_id=sample_role.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_client(client, sample_user):
    """A logged-in test client."""
    from flask_login import login_user
    from models import User
    with client.session_transaction() as sess:
        # Simulate login
        pass
    return client
