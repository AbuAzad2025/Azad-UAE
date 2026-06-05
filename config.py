import os
import re
import secrets
import logging
import socket
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, "instance")
os.makedirs(instance_dir, exist_ok=True)

load_dotenv(os.path.join(basedir, ".env"))


def _redis_available(host: str = "localhost", port: int = 6379, timeout: float = 0.5) -> bool:
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
    Production default: off (safe). Non-production / DEBUG: on (dev learning).
    """
    explicit = os.environ.get("AI_ORM_LISTENERS_ENABLED")
    if explicit is not None:
        return _bool(explicit, False)
    app_env = (os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "production").strip().lower()
    debug = _bool(os.environ.get("DEBUG"), False)
    if app_env == "production" and not debug:
        return False
    return True


class Config:
    """Application Configuration"""
    
    FLASK_APP = os.environ.get("FLASK_APP", "app:create_app")
    APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "production"))
    DEBUG = _bool(os.environ.get("DEBUG"), False)

    # SQLAlchemy AI/neural listeners (models/events.py) — off in production by default
    AI_ORM_LISTENERS_ENABLED = ai_orm_listeners_enabled()
    
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        secret_file = os.path.join(instance_dir, "secret_key")
        if os.path.exists(secret_file):
            try:
                with open(secret_file, "r", encoding="utf-8") as f:
                    SECRET_KEY = f.read().strip()
            except Exception:
                SECRET_KEY = secrets.token_hex(32)
        else:
            SECRET_KEY = secrets.token_hex(32)
            try:
                with open(secret_file, "w", encoding="utf-8") as f:
                    f.write(SECRET_KEY)
            except Exception:
                pass
        logging.info("[Dev] SECRET_KEY loaded/generated for development (set SECRET_KEY env in production)")
    
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _int("PORT", 5000)
    
    WTF_CSRF_EXEMPT_LIST = [
        '/sales/api/calculate-totals',
        '/purchases/api/calculate-totals',
        '/ledger/api/calculate-journal-balance'
    ]
    
    _db_uri = os.environ.get("DATABASE_URL") or "postgresql+psycopg2://postgres@localhost:5432/azad_uae"
    
    # Handle PythonAnywhere specific postgres URL format if needed
    if _db_uri.startswith("postgres://"):
        _db_uri = _db_uri.replace("postgres://", "postgresql+psycopg2://", 1)
    if _db_uri.startswith("postgresql://"):
        _db_uri = _db_uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 10,
        "max_overflow": 20,
    }
    
    if _db_uri.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"options": "-c statement_timeout=5000"}
    
    SQLALCHEMY_ECHO = False
    
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False
    
    COMPRESS_MIMETYPES = [
        'text/html', 'text/css', 'text/xml', 'text/plain',
        'application/json', 'application/javascript',
        'application/xml', 'application/xhtml+xml'
    ]
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    COMPRESS_ALGORITHM = 'gzip'
    
    SESSION_COOKIE_NAME = "garage_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=_int("REMEMBER_DAYS", 14))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_HOURS", 12))
    
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 16) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {
        'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp'},
        'documents': {'.pdf', '.xlsx', '.xls', '.csv'},
    }
    
    MAX_LOGIN_ATTEMPTS = _int("MAX_LOGIN_ATTEMPTS", 5)
    LOGIN_BLOCK_DURATION = _int("LOGIN_BLOCK_DURATION_MINUTES", 15) * 60
    
    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)
    WTF_CSRF_TIME_LIMIT = None
    
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")
    CORS_SUPPORTS_CREDENTIALS = True
    
    RATELIMIT_DEFAULT = "10000 per day;1000 per hour"
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
    CACHE_KEY_PREFIX = "garage_simple"
    
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
    
    DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "AED")

    # --- Feature Flags (Accounting Modernization) ---
    # Phase 1: Dynamic GL Mapping
    # When False (default): legacy hardcoded GL code lookups remain active.
    ENABLE_DYNAMIC_GL_MAPPING = _bool(os.environ.get("ENABLE_DYNAMIC_GL_MAPPING"), True)

    # Phase 3-4: Moving Weighted Average Cost (MWAC)
    # When False: stock valuation uses Last Purchase Cost.
    ENABLE_MWAC = _bool(os.environ.get("ENABLE_MWAC"), True)

    # Phase 5: Landed Cost Capitalization
    # When False: freight/customs/insurance are expensed directly to P&L.
    ENABLE_LANDED_COST_CAPITALIZATION = _bool(os.environ.get("ENABLE_LANDED_COST_CAPITALIZATION"), False)

    # Phase 6: Exchange Rate Framework
    # When False: exchange rates are not locked on posted documents.
    ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK = _bool(os.environ.get("ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK"), False)

    # Phase 7: Advanced Reconciliation
    # When False: stock-to-GL reconciliation dashboards are hidden.
    ENABLE_ADVANCED_RECONCILIATION = _bool(os.environ.get("ENABLE_ADVANCED_RECONCILIATION"), False)

    # Phase 9: Localization Framework
    # When False: regional tax/invoice engines are disabled.
    ENABLE_LOCALIZATION_FRAMEWORK = _bool(os.environ.get("ENABLE_LOCALIZATION_FRAMEWORK"), False)

    CURRENCY_API_PROVIDER = os.environ.get("CURRENCY_API_PROVIDER", "exchangerate-api")
    CURRENCY_API_KEY = os.environ.get("CURRENCY_API_KEY", "")
    CURRENCY_API_URL = os.environ.get("CURRENCY_API_URL", "https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}")
    
    CURRENCY_API_FALLBACKS = [
        "https://api.exchangerate-api.com/v4/latest/{base}",
        "https://open.er-api.com/v6/latest/{base}",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base_lower}.json",
        "https://api.freecurrencyapi.com/v1/latest?base_currency={base}",
        "https://api.frankfurter.dev/v1/latest?base={base}",
    ]

    # Cache for accounting currency service (CurrencyService)
    CURRENCY_CACHE_TIMEOUT = _int("CURRENCY_CACHE_TIMEOUT", 3600)

    # Cache for display-only online rates (ExchangeRateService) — navbar / fxModal
    CURRENCY_ONLINE_CACHE_TIMEOUT = _int("CURRENCY_ONLINE_CACHE_TIMEOUT", 43200)

    CURRENCY_API_TIMEOUT = _int("CURRENCY_API_TIMEOUT", 5)
    
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Azad Smart Systems")
    COMPANY_NAME_AR = os.environ.get("COMPANY_NAME_AR", "شركة أزاد للأنظمة الذكية")
    COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "فلسطين - رام الله | Palestine - Ramallah")
    COMPANY_ADDRESS_EN = os.environ.get("COMPANY_ADDRESS_EN")
    if not COMPANY_ADDRESS_EN:
        if "|" in COMPANY_ADDRESS:
            _parts = [p.strip() for p in COMPANY_ADDRESS.split("|") if p.strip()]
            if _parts:
                def _arabic_count(s: str) -> int:
                    return len(re.findall(r"[\u0600-\u06FF]", s))
                COMPANY_ADDRESS_EN = min(_parts, key=_arabic_count)
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
    DEVELOPER_CREDIT = os.environ.get("DEVELOPER_CREDIT", "تطوير وبرمجة: م. أحمد غنام | Developed by Eng. Ahmad Ghannam - Azad Systems")
    DEVELOPER_WEBSITE = os.environ.get("DEVELOPER_WEBSITE", "https://azadsystems.com")
    DEVELOPER_PHONE = os.environ.get("DEVELOPER_PHONE", "+971500000000")
    DEVELOPER_EMAIL = os.environ.get("DEVELOPER_EMAIL", "dev@example.com")
    DEVELOPER_WHATSAPP = os.environ.get("DEVELOPER_WHATSAPP", "+972562150193")
    DEVELOPER_LOGO = os.environ.get("DEVELOPER_LOGO", "assets/brand/azad/logos/logo.png")
    APP_VERSION = "2.0.0"
    
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "ar")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "Asia/Dubai")
    LANGUAGES = {
        'ar': 'العربية',
        'en': 'English'
    }
    
    OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "owner")
    OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "")
    OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@example.com")
    
    CARD_ENCRYPTION_KEY = os.environ.get("CARD_ENCRYPTION_KEY", "")
    if not CARD_ENCRYPTION_KEY:
        key_path = os.path.join(instance_dir, ".card_encryption_key")
        try:
            if os.path.exists(key_path):
                with open(key_path, "r", encoding="utf-8") as f:
                    CARD_ENCRYPTION_KEY = (f.read() or "").strip()
        except Exception:
            CARD_ENCRYPTION_KEY = ""

        if not CARD_ENCRYPTION_KEY:
            CARD_ENCRYPTION_KEY = secrets.token_hex(32)
            try:
                os.makedirs(instance_dir, exist_ok=True)
                with open(key_path, "w", encoding="utf-8") as f:
                    f.write(CARD_ENCRYPTION_KEY)
            except Exception:
                pass
    
    ALLOW_CARD_DECRYPTION = _bool(os.environ.get("ALLOW_CARD_DECRYPTION"), False)
    
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
    ITEMS_PER_PAGE = _int("ITEMS_PER_PAGE", 20)
    
    DEFAULT_PRODUCT_IMAGE = "assets/shared/placeholders/no-product.png"
    
    BACKUP_DIR = os.path.join(instance_dir, "backups")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    BACKUP_KEEP_LAST = _int("BACKUP_KEEP_LAST", 10)
    BACKUP_SCHEDULE = "0 2 * * *"
    
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
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
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
    
    WHATSAPP_ENABLED = _bool(os.environ.get("WHATSAPP_ENABLED"), False)
    WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
    WHATSAPP_PHONE_NUMBER = os.environ.get("WHATSAPP_PHONE_NUMBER", "")


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
    if not owner_password or owner_password == "owner@2025!secure":
        raise RuntimeError("OWNER_PASSWORD must be set and not default in production!")
    
    db_uri = cfg.SQLALCHEMY_DATABASE_URI
    if db_uri.startswith("sqlite"):
        raise RuntimeError("SQLite is not allowed in production. Use PostgreSQL/MySQL.")
    
    if not cfg.SESSION_COOKIE_SECURE:
        raise RuntimeError("SESSION_COOKIE_SECURE must be True in production!")
    
    base_url = getattr(cfg, "BASE_URL", "")
    if base_url and not base_url.startswith("https://"):
        logging.warning(f"Production Warning: BASE_URL ({base_url}) should start with https://. Please update your .env file.")
        # We won't raise an error here to prevent deployment crashes, but links might be incorrect.
    
    logging.info("Production configuration check complete")


# Suppress SQLAlchemy engine logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

