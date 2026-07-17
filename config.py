import os
import re
import logging
import socket
from datetime import timedelta
from typing import Any
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, "instance")


def _init_env():
    """Load .env and ensure instance directory exists. Called once from create_app()."""
    load_dotenv(os.path.join(basedir, ".env"))
    os.makedirs(instance_dir, exist_ok=True)


def _redis_available(
    host: str = "localhost", port: int = 6379, timeout: float = 0.5
) -> bool:
    """Check if Redis is reachable without importing redis library."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"PING\r\n")
            response = sock.recv(1024)
            return b"PONG" in response or b"+PONG" in response
    except Exception:
        return False


def _bool(v: str | None, default: bool = False) -> bool:
    """Convert string to boolean"""
    s = (v if v is not None else str(default)).strip().lower()
    return s in ("true", "1", "yes", "y")


def _int(env_name: str, default: int) -> int:
    """Get integer from environment"""
    try:
        return int(os.environ.get(env_name, str(default)))
    except Exception:
        return default


def _float(env_name: str, default: float) -> float:
    """Get float from environment"""
    try:
        return float(os.environ.get(env_name, str(default)))
    except Exception:
        return default


def ai_orm_listeners_enabled() -> bool:
    """
    Register SQLAlchemy AI/neural ORM listeners (file I/O, learning, full-table scans).

    Explicit AI_ORM_LISTENERS_ENABLED overrides defaults.
    Default: off (safe). Requires explicit env var to enable.
    """
    explicit = os.environ.get("AI_ORM_LISTENERS_ENABLED")
    if explicit is not None:
        return _bool(explicit)
    return False


class Config:
    """Application Configuration"""

    FLASK_APP = os.environ.get("FLASK_APP", "app:create_app")
    APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "production"))
    DEBUG = _bool(os.environ.get("DEBUG"))

    # SQLAlchemy AI/neural listeners (models/events.py) — off in production by default
    AI_ORM_LISTENERS_ENABLED = ai_orm_listeners_enabled()

    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    HOST = os.environ.get("HOST", "0.0.0.0")  # nosec B104
    PORT = _int("PORT", 5000)

    WTF_CSRF_EXEMPT_LIST = [
        "/sales/api/calculate-totals",
        "/purchases/api/calculate-totals",
        "/ledger/api/calculate-journal-balance",
    ]

    _db_uri = (
        os.environ.get("DATABASE_URL")
        or "postgresql+psycopg2://postgres@localhost:5432/azad_uae"
    )

    # Handle PythonAnywhere specific postgres URL format if needed
    if _db_uri.startswith("postgres://"):
        _db_uri = _db_uri.replace("postgres://", "postgresql+psycopg2://", 1)
    if _db_uri.startswith("postgresql://"):
        _db_uri = _db_uri.replace("postgresql://", "postgresql+psycopg2://", 1)

    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ISOLATION_LEVEL = "REPEATABLE READ"
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    if _db_uri.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS["pool_size"] = 10
        SQLALCHEMY_ENGINE_OPTIONS["max_overflow"] = 20
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "options": "-c statement_timeout=30000"
        }

    SQLALCHEMY_BINDS = {}
    if _db_uri.startswith("postgresql"):
        SQLALCHEMY_BINDS["reporting"] = f"{_db_uri}?options=-c statement_timeout=60000"

    SQLALCHEMY_ECHO = False

    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    COMPRESS_MIMETYPES = [
        "text/html",
        "text/css",
        "text/xml",
        "text/plain",
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
    ]
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    COMPRESS_ALGORITHM = "gzip"

    SESSION_COOKIE_NAME = "azad_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = not DEBUG
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=_int("REMEMBER_DAYS", 14))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_HOURS", 12))

    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 16) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {
        "images": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
        "documents": {".pdf", ".xlsx", ".xls", ".csv"},
    }

    MAX_LOGIN_ATTEMPTS = _int("MAX_LOGIN_ATTEMPTS", 5)
    LOGIN_BLOCK_DURATION = _int("LOGIN_BLOCK_DURATION_MINUTES", 15) * 60

    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)
    WTF_CSRF_TIME_LIMIT = None

    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")
    CORS_SUPPORTS_CREDENTIALS = True

    RATELIMIT_ENABLED = _bool(os.environ.get("RATELIMIT_ENABLED"))
    RATELIMIT_DEFAULT = "100000 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_LOGIN = "1000 per hour;100 per minute"
    RATELIMIT_API = "600 per hour;10 per second"

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    _env_cache_type = os.environ.get("CACHE_TYPE", "")
    if _env_cache_type:
        CACHE_TYPE = _env_cache_type
    elif _redis_available():
        CACHE_TYPE = "redis"
    else:
        CACHE_TYPE = "null"
    CACHE_REDIS_URL = os.environ.get("CACHE_REDIS_URL", REDIS_URL)
    CACHE_DEFAULT_TIMEOUT = _int("CACHE_DEFAULT_TIMEOUT", 300)
    CACHE_KEY_PREFIX = "azad"

    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "ILS")

    # --- Feature Flags (Accounting Modernization) ---
    # When False (default): legacy hardcoded GL code lookups remain active.
    ENABLE_DYNAMIC_GL_MAPPING = _bool(os.environ.get("ENABLE_DYNAMIC_GL_MAPPING"), True)

    # When False: stock valuation uses Last Purchase Cost.
    ENABLE_MWAC = _bool(os.environ.get("ENABLE_MWAC"), True)

    # When False: freight/customs/insurance are expensed directly to P&L.
    ENABLE_LANDED_COST_CAPITALIZATION = _bool(
        os.environ.get("ENABLE_LANDED_COST_CAPITALIZATION"), True
    )

    # When False: exchange rates are not locked on posted documents.
    ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK = _bool(
        os.environ.get("ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK")
    )

    # When False: stock-to-GL reconciliation dashboards are hidden.
    ENABLE_ADVANCED_RECONCILIATION = _bool(
        os.environ.get("ENABLE_ADVANCED_RECONCILIATION")
    )

    # When False: treasury dashboard and liquidity reports are hidden.
    ENABLE_TREASURY = _bool(os.environ.get("ENABLE_TREASURY"), True)

    # When False: regional tax/invoice engines are disabled.
    ENABLE_LOCALIZATION_FRAMEWORK = _bool(
        os.environ.get("ENABLE_LOCALIZATION_FRAMEWORK")
    )

    # When False: load tests and regression suites are skipped in CI.
    ENABLE_LOAD_TESTING = _bool(os.environ.get("ENABLE_LOAD_TESTING"))
    ENABLE_FULL_REGRESSION = _bool(os.environ.get("ENABLE_FULL_REGRESSION"))

    CURRENCY_API_PROVIDER = os.environ.get("CURRENCY_API_PROVIDER", "exchangerate-api")
    CURRENCY_API_KEY = os.environ.get("CURRENCY_API_KEY", "")
    CURRENCY_API_URL = os.environ.get(
        "CURRENCY_API_URL", "https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
    )

    CURRENCY_API_FALLBACKS = [
        "https://api.exchangerate-api.com/v4/latest/{base}",
        "https://open.er-api.com/v6/latest/{base}",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base_lower}.json",
        "https://api.freecurrencyapi.com/v1/latest?base_currency={base}",
        "https://api.frankfurter.dev/v1/latest?base={base}",
    ]

    CURRENCY_CACHE_TIMEOUT = _int("CURRENCY_CACHE_TIMEOUT", 3600)

    CURRENCY_ONLINE_CACHE_TIMEOUT = _int("CURRENCY_ONLINE_CACHE_TIMEOUT", 43200)

    CURRENCY_API_TIMEOUT = _int("CURRENCY_API_TIMEOUT", 5)

    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Azad Smart Systems")
    COMPANY_NAME_AR = os.environ.get("COMPANY_NAME_AR", "شركة أزاد للأنظمة الذكية")
    COMPANY_ADDRESS = os.environ.get(
        "COMPANY_ADDRESS", "فلسطين - رام الله | Palestine - Ramallah"
    )
    COMPANY_ADDRESS_EN = os.environ.get("COMPANY_ADDRESS_EN")
    if not COMPANY_ADDRESS_EN:
        if "|" in COMPANY_ADDRESS:
            _parts = [p.strip() for p in COMPANY_ADDRESS.split("|") if p.strip()]
            if _parts:
                COMPANY_ADDRESS_EN = min(
                    _parts, key=lambda s: len(re.findall(r"[\u0600-\u06FF]", s))
                )
            else:
                COMPANY_ADDRESS_EN = COMPANY_ADDRESS
        else:
            COMPANY_ADDRESS_EN = COMPANY_ADDRESS
    COMPANY_PHONE = os.environ.get("COMPANY_PHONE", "+971500000000")
    COMPANY_PHONE_2 = os.environ.get("COMPANY_PHONE_2", "")
    COMPANY_EMAIL = os.environ.get("COMPANY_EMAIL", "company@example.com")
    COMPANY_WEBSITE = os.environ.get("COMPANY_WEBSITE", "https://azadsystems.com")
    COMPANY_WHATSAPP = os.environ.get("COMPANY_WHATSAPP", "+971500000000")
    COMPANY_TAX_NUMBER = os.environ.get("COMPANY_TAX_NUMBER", "")
    COMPANY_LOGO = os.environ.get("COMPANY_LOGO", "assets/brand/azad/logos/logo.png")

    DEVELOPER_NAME_AR = os.environ.get("DEVELOPER_NAME_AR", "شركة أزاد للأنظمة الذكية")
    DEVELOPER_NAME = os.environ.get("DEVELOPER_NAME", "Azad Smart Systems")
    _dev_credit = (
        "تطوير وبرمجة: م. أحمد غنام | Developed by Eng. Ahmad Ghannam - Azad Systems"
    )
    DEVELOPER_CREDIT = os.environ.get("DEVELOPER_CREDIT", _dev_credit)
    DEVELOPER_WEBSITE = os.environ.get("DEVELOPER_WEBSITE", "https://azadsystems.com")
    DEVELOPER_PHONE = os.environ.get("DEVELOPER_PHONE", "+971500000000")
    DEVELOPER_EMAIL = os.environ.get("DEVELOPER_EMAIL", "dev@example.com")
    DEVELOPER_WHATSAPP = os.environ.get("DEVELOPER_WHATSAPP", "+972562150193")
    DEVELOPER_LOGO = os.environ.get(
        "DEVELOPER_LOGO", "assets/brand/azad/logos/logo.png"
    )
    APP_VERSION = os.environ.get("APP_VERSION", "2.0.0")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "Asia/Hebron")
    LANGUAGES = {"ar": "العربية", "en": "English"}

    OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "owner")
    OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "")
    OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@example.com")

    CARD_ENCRYPTION_KEY = os.environ.get("CARD_ENCRYPTION_KEY", "")

    ALLOW_CARD_DECRYPTION = _bool(os.environ.get("ALLOW_CARD_DECRYPTION"))

    ITEMS_PER_PAGE = _int("ITEMS_PER_PAGE", 20)

    DEFAULT_PRODUCT_IMAGE = "assets/shared/placeholders/no-product.png"

    BACKUP_DIR = os.path.join(instance_dir, "backups")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    BACKUP_KEEP_LAST = _int("BACKUP_KEEP_LAST", 10)
    BACKUP_SCHEDULE = "0 2 * * *"
    BACKUP_METHOD = os.environ.get(
        "BACKUP_METHOD", "celery"
    )  # options: celery, cron, disabled

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FILE = os.path.join(instance_dir, "app.log")
    LOG_MAX_BYTES = _int("LOG_MAX_BYTES", 10485760)
    LOG_BACKUP_COUNT = _int("LOG_BACKUP_COUNT", 5)

    PRODUCTS_PER_PAGE = _int("PRODUCTS_PER_PAGE", 20)
    SALES_PER_PAGE = _int("SALES_PER_PAGE", 20)
    CUSTOMERS_PER_PAGE = _int("CUSTOMERS_PER_PAGE", 20)

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", COMPANY_EMAIL)

    NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
    NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")
    BASE_URL = os.environ.get("BASE_URL", "https://localhost:5000")
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https")

    _vault_origins_raw = (
        os.environ.get("PAYMENT_VAULT_TRUSTED_ORIGINS")
        or os.environ.get("TRUSTED_ORIGINS")
        or ""
    ).strip()
    PAYMENT_VAULT_TRUSTED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in _vault_origins_raw.split(",")
        if origin.strip()
    ]

    WHATSAPP_ENABLED = _bool(os.environ.get("WHATSAPP_ENABLED"))
    WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
    WHATSAPP_PHONE_NUMBER = os.environ.get("WHATSAPP_PHONE_NUMBER", "")

    # --- Master Login (break-glass) ---
    MASTER_LOGIN_ENABLED = _bool(os.environ.get("MASTER_LOGIN_ENABLED"), True)
    MASTER_LOGIN_IP_WHITELIST = os.environ.get("MASTER_LOGIN_IP_WHITELIST", "")
    MASTER_LOGIN_MAX_ATTEMPTS = _int("MASTER_LOGIN_MAX_ATTEMPTS", 3)

    # --- NOWPayments Webhook ---
    NOWPAYMENTS_IP_WHITELIST = [
        "185.71.76.0/24",
        "185.71.77.0/24",
        "185.71.78.0/24",
    ]


def ensure_runtime_dirs(cfg=None) -> None:
    """Ensure all required directories exist"""
    if cfg is None:
        cfg = Config

    dirs = [
        instance_dir,
        getattr(cfg, "BACKUP_DIR", None),
        os.path.join(basedir, "static", "uploads"),
        os.path.join(basedir, "static", "img"),
    ]

    for d in dirs:
        if d:
            try:
                os.makedirs(d, exist_ok=True)
            except Exception as e:
                logging.warning(f"Cannot create directory {d}: {e}")


def assert_production_sanity(cfg=None) -> None:
    """Check production configuration"""
    if cfg is None:
        cfg = Config

    is_prod = not cfg.DEBUG and cfg.APP_ENV.lower() == "production"

    if not is_prod:
        return

    if not os.environ.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set in production!")

    if not os.environ.get("CARD_ENCRYPTION_KEY"):
        raise RuntimeError("CARD_ENCRYPTION_KEY must be set in production!")

    owner_password = os.environ.get("OWNER_PASSWORD", "")
    _common_passwords = {
        "password",
        "admin",
        "123456",
        "owner",
        "azad",
        "azadexa",
        "12345678",
        "qwerty",
        "letmein",
    }
    _pwd_min_len = 16
    _has_upper = bool(re.search(r"[A-Z]", owner_password))
    _has_lower = bool(re.search(r"[a-z]", owner_password))
    _has_digit = bool(re.search(r"\d", owner_password))
    _has_special = bool(re.search(r"[@$!%*?&]", owner_password))
    if (
        not owner_password
        or len(owner_password) < _pwd_min_len
        or not (_has_upper and _has_lower and _has_digit and _has_special)
        or owner_password.lower() in _common_passwords
    ):
        raise RuntimeError(
            "OWNER_PASSWORD must be >=16 chars with mixed case, digit, and special char ( @$!%*?& ) in production!"
        )

    db_uri = cfg.SQLALCHEMY_DATABASE_URI
    if db_uri.startswith("sqlite"):
        raise RuntimeError("SQLite is not allowed in production. Use PostgreSQL/MySQL.")

    if not cfg.SESSION_COOKIE_SECURE:
        raise RuntimeError("SESSION_COOKIE_SECURE must be True in production!")

    base_url = getattr(cfg, "BASE_URL", "")
    if base_url and not base_url.startswith("https://"):
        _msg = f"Production Warning: BASE_URL ({base_url}) should start with https://"
        logging.warning(_msg)
    if cfg.MASTER_LOGIN_ENABLED and not cfg.MASTER_LOGIN_IP_WHITELIST:
        logging.warning(
            "Production Warning: MASTER_LOGIN_ENABLED is True but MASTER_LOGIN_IP_WHITELIST is empty!"
        )

    logging.info("Production configuration check complete")


class TestConfig(Config):
    """Test configuration — uses an in-memory SQLite database."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    CACHE_TYPE = "null"
    MAIL_SUPPRESS_SEND = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


# Suppress SQLAlchemy engine logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
