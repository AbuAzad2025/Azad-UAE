import os
print("DEBUG: App file starting load...", flush=True)
import re
import sys
import uuid
from datetime import datetime, timezone
import time
from decimal import Decimal
from flask import Flask, render_template, request, g, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from werkzeug.routing import BuildError

from config import Config, ensure_runtime_dirs, assert_production_sanity
from extensions import (
    db, migrate, login_manager, csrf, limiter, mail,
    init_extensions, setup_logging
)
from utils.monitoring import setup_advanced_logging
from utils.enhanced_logging import setup_enhanced_logging
from utils.asset_compression import register_compression_cli
from config_redis import init_redis
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from flask_compress import Compress
    COMPRESS_AVAILABLE = True
except ImportError:
    COMPRESS_AVAILABLE = False


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Ensure runtime directories exist
    ensure_runtime_dirs(config_class)
    
    # Verify production sanity (Database check)
    assert_production_sanity(config_class)
    
    # Initialize Extensions
    setup_logging(app)
    init_extensions(app)

    # Initialize User Loader for Flask-Login
    from extensions import login_manager
    from models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    setup_advanced_logging(app)
    setup_enhanced_logging(app)
    
    # --- SYSTEM INTEGRITY CHECK (MASTER KEY & CORE DATA) ---
    # This ensures that even after a full DB wipe, the system regenerates
    # essential data (Currencies, Accounts, Warehouses, Roles, Admin User)
    # automatically on restart.
    print("DEBUG: System Integrity Check...", flush=True)
    if not os.environ.get("SKIP_SYSTEM_INTEGRITY"):
        from utils.system_init import ensure_system_integrity
        try:
            ensure_system_integrity(app)
            app.logger.info("[OK] System integrity verified (Master Key & Core Data Active)")
        except Exception as e:
            app.logger.error(f"[ERROR] System integrity check failed: {e}")
            import traceback
            traceback.print_exc()
    # -------------------------------------------
    
    # Proxy Fix for Nginx/Cloudflare
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Register Blueprints
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.sales import sales_bp
    from routes.products import products_bp
    from routes.customers import customers_bp
    from routes.reports import reports_bp
    # from routes.settings import settings_bp
    from routes.api import api_bp
    from routes.api_enhanced import api_enhanced_bp
    from routes.suppliers import suppliers_bp
    from routes.purchases import purchases_bp
    from routes.expenses import expenses_bp
    from routes.ledger import ledger_bp
    from routes.owner import owner_bp
    from routes.payments import payments_bp
    # from routes.notifications import notifications_bp
    from routes.warehouse import warehouse_bp
    from routes.language import language_bp
    from routes.tenants import tenants_bp
    from routes.payroll import payroll_bp
    def _make_ai_fallback(ai_import_error: str):
        from flask import Blueprint, flash, redirect, url_for
        ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

        @ai_bp.route('/assistant')
        @login_required
        def assistant_page():
            flash(f"AI Module failed to load on server start. Please check logs. Error: {ai_import_error}", "error")
            return redirect(url_for('main.dashboard'))

        @ai_bp.route('/config')
        @login_required
        def config():
            flash(f"AI Module failed to load on server start. Please check logs. Error: {ai_import_error}", "error")
            return redirect(url_for('main.dashboard'))

        @ai_bp.route('/chat', methods=['POST'])
        def chat():
            return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/recommend-price', methods=['POST'])
        def recommend_price(): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/check-stock', methods=['POST'])
        def check_stock(): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/analyze-customer/<int:customer_id>', methods=['GET'])
        def analyze_customer(customer_id): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/exchange-rate/<currency>', methods=['GET'])
        def exchange_rate(currency): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/search-market-price/<int:product_id>', methods=['GET'])
        def search_market_price(product_id): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/find-compatible/<int:product_id>', methods=['GET'])
        def find_compatible(product_id): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/upload-excel', methods=['POST'])
        def upload_excel(): return {"error": "AI Module Unavailable"}, 503

        @ai_bp.route('/<path:path>')
        def catch_all(path):
            try:
                from flask import session
                if not session.get('ai_unavailable_notified'):
                    flash("المساعد الذكي غير متاح حالياً بسبب إعدادات غير مكتملة.", "warning")
                    session['ai_unavailable_notified'] = True
            except Exception:
                pass
            return redirect(url_for('main.dashboard'))

        return ai_bp

    if os.environ.get("DISABLE_AI"):
        _ai_enabled = False
        ai_bp = _make_ai_fallback("AI disabled by server configuration")
    else:
        try:
            from routes.ai import ai_bp
            _ai_enabled = True
        except Exception as e:
            ai_import_error = str(e)
            print(f"AI Blueprint Import Error: {ai_import_error}")
            import traceback
            traceback.print_exc()
            _ai_enabled = False
            ai_bp = _make_ai_fallback(ai_import_error)
            return redirect(url_for('main.dashboard'))
    from routes.users import users_bp
    from routes.cheques import cheques_bp
    from routes.returns import returns_bp
    from routes.advanced_ledger import advanced_ledger_bp
    from routes.admin_ledger import admin_ledger_bp
    from routes.gamification import gamification_bp
    from routes.pos import pos_bp
    from routes.store import store_bp
    from routes.shop import shop_bp
    from routes.whatsapp import whatsapp_bp
    from routes.monitoring import monitoring_bp
    from routes.public import public_bp
    from routes.payment_vault import payment_vault_bp
    from routes.api_analytics import api_analytics_bp
    from routes.api_docs import api_docs_bp
    from routes.graphql import graphql_bp
    from routes.branches import branches_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(api_enhanced_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(language_bp)
    app.register_blueprint(tenants_bp)
    # app.register_blueprint(branches_bp) # Duplicate removed
    app.register_blueprint(payroll_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(cheques_bp)
    app.register_blueprint(returns_bp)
    app.register_blueprint(advanced_ledger_bp)
    app.register_blueprint(admin_ledger_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(owner_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(payment_vault_bp)
    app.register_blueprint(api_analytics_bp)
    app.register_blueprint(api_docs_bp)
    app.register_blueprint(graphql_bp)
    app.register_blueprint(branches_bp)
    
    @app.before_request
    def storefront_custom_domain_redirect():
        """Route custom domain / subdomain to the tenant storefront catalog."""
        path = request.path or '/'
        if path.startswith(('/s/', '/static/', '/auth/', '/store/', '/api/', '/owner/', '/admin')):
            return None
        from services.store_service import StoreService
        store = StoreService.get_store_by_host(request.host)
        if store and StoreService.is_store_publicly_available(store):
            from flask import redirect, url_for
            return redirect(url_for('shop.catalog', slug=store.store_slug))
        return None

    # Error Handlers
    # from utils.error_handlers import register_error_handlers
    # register_error_handlers(app)
    
    @app.template_global()
    def tenant_document_logo(settings=None, tenant_id=None):
        from utils.tenant_branding import document_logo_relative_path
        return document_logo_relative_path(settings, tenant_id)

    # Context Processors
    @app.context_processor
    def utility_processor():
        from utils.helpers import format_currency, timeago
        from utils.number_to_arabic import number_to_arabic_words
        from utils.constants import CURRENCIES
        from utils.i18n import t, is_rtl, get_current_language

        def get_currency_symbol(code):
            for c_code, data in CURRENCIES:
                if c_code == code:
                    return data.get('symbol', code)
            return code

        tenant_name_ar = ''
        tenant_name = ''
        tenant_phone = ''
        tenant_email = ''
        tenant_address = ''
        tenant_logo_url = ''
        tenant_logo_dark_url = ''
        tenant_favicon_url = ''
        tenant_default_currency = ''
        tenant_enable_tax = None
        tenant_default_tax_rate = None
        try:
            from models import Tenant
            from models.invoice_settings import InvoiceSettings
            tenant = Tenant.get_current()
            if tenant:
                tenant_name_ar = (tenant.name_ar or '').strip()
                tenant_name = (tenant.name_en or tenant.name or '').strip()
                tenant_phone = (tenant.phone_1 or tenant.mobile or '').strip()
                tenant_email = (tenant.email or '').strip()
                tenant_address = (tenant.address_ar or tenant.address_en or '').strip()
                tenant_logo_url = (tenant.logo_url or '').strip()
                tenant_logo_dark_url = (tenant.logo_dark_url or '').strip()
                tenant_favicon_url = (tenant.favicon_url or '').strip()
                tenant_default_currency = (tenant.default_currency or '').strip()
                tenant_enable_tax = bool(getattr(tenant, "enable_tax", True))
                tenant_default_tax_rate = getattr(tenant, "default_tax_rate", None)
            if not tenant_name_ar:
                inv = InvoiceSettings.get_active()
                if inv:
                    tenant_name_ar = (inv.company_name_ar or '').strip()
                    tenant_name = (inv.company_name_en or '').strip() or tenant_name
                    tenant_phone = (inv.phone_1 or '').strip() or tenant_phone
                    tenant_email = (inv.email or '').strip() or tenant_email
                    tenant_address = (inv.address_ar or inv.address_en or '').strip() or tenant_address
                    tenant_logo_url = (inv.logo_url or '').strip() or tenant_logo_url
            if tenant:
                from utils.tenant_branding import resolve_tenant_branding
                branding = resolve_tenant_branding(tenant.id)
                tenant_logo_url = branding.get('logo_url') or tenant_logo_url
                tenant_logo_dark_url = branding.get('logo_dark_url') or tenant_logo_dark_url
                tenant_favicon_url = branding.get('favicon_url') or tenant_favicon_url
                if not tenant_name_ar:
                    tenant_name_ar = branding.get('company_name_ar') or tenant_name_ar
                if not tenant_name:
                    tenant_name = branding.get('company_name_en') or tenant_name
        except Exception:
            pass

        try:
            from models.system_settings import SystemSettings
            sys_settings = SystemSettings.get_current()
            developer_name_ar = (sys_settings.get_custom_setting('developer_name_ar') or '').strip() or app.config.get('DEVELOPER_NAME_AR', '')
            developer_name = (sys_settings.get_custom_setting('developer_name') or '').strip() or app.config.get('DEVELOPER_NAME', '')
            developer_credit = (sys_settings.get_custom_setting('developer_credit') or '').strip() or app.config.get('DEVELOPER_CREDIT', '')
            developer_phone = (sys_settings.get_custom_setting('developer_phone') or '').strip() or app.config.get('DEVELOPER_PHONE', '')
            developer_email = (sys_settings.get_custom_setting('developer_email') or '').strip() or app.config.get('DEVELOPER_EMAIL', '')
            developer_website = (sys_settings.get_custom_setting('developer_website') or '').strip() or app.config.get('DEVELOPER_WEBSITE', '')
            developer_whatsapp = (sys_settings.get_custom_setting('developer_whatsapp') or '').strip() or app.config.get('DEVELOPER_WHATSAPP', '')
            developer_logo_raw = (sys_settings.get_custom_setting('developer_logo') or '').strip()
            if developer_logo_raw and (":\\" in developer_logo_raw or ":/" in developer_logo_raw):
                developer_logo_raw = ""
            if developer_logo_raw.startswith("/static/"):
                developer_logo_raw = developer_logo_raw[len("/static/"):]
            if developer_logo_raw.startswith("static/"):
                developer_logo_raw = developer_logo_raw[len("static/"):]
            developer_logo = developer_logo_raw or app.config.get('DEVELOPER_LOGO', 'assets/brand/azad/logos/logo.png')
            system_default_currency = (sys_settings.default_currency or '').strip() or 'AED'
            system_currency_symbol = (sys_settings.currency_symbol or '').strip() or system_default_currency
            system_currency_position = (sys_settings.currency_position or '').strip() or 'after'
            system_decimal_places = sys_settings.decimal_places if isinstance(sys_settings.decimal_places, int) else 2
            system_enable_tax = bool(getattr(sys_settings, "enable_tax", True))
            system_default_tax_rate = getattr(sys_settings, "default_tax_rate", None)
        except Exception:
            developer_name_ar = app.config.get('DEVELOPER_NAME_AR', '')
            developer_name = app.config.get('DEVELOPER_NAME', '')
            developer_credit = app.config.get('DEVELOPER_CREDIT', '')
            developer_phone = app.config.get('DEVELOPER_PHONE', '')
            developer_email = app.config.get('DEVELOPER_EMAIL', '')
            developer_website = app.config.get('DEVELOPER_WEBSITE', '')
            developer_whatsapp = app.config.get('DEVELOPER_WHATSAPP', '')
            developer_logo = app.config.get('DEVELOPER_LOGO', 'assets/brand/azad/logos/logo.png')
            system_default_currency = 'AED'
            system_currency_symbol = 'AED'
            system_currency_position = 'after'
            system_decimal_places = 2
            system_enable_tax = True
            system_default_tax_rate = None

        def _normalize_whatsapp_link(value):
            digits = re.sub(r"\D+", "", value or "")
            if digits.startswith("00"):
                digits = digits[2:]
            return digits

        developer_whatsapp_link = _normalize_whatsapp_link(developer_whatsapp or developer_phone)

        from flask_login import current_user
        from utils.constants import PERMISSIONS, PERMISSION_CODES, CUSTOMER_TYPES, PAYMENT_STATUSES, SALE_STATUSES, PAYMENT_METHODS, USER_ROLES
        from utils.branching import get_active_branch, get_active_branch_mode
        current_user_permissions = []
        if current_user.is_authenticated and getattr(current_user, 'has_permission', None):
            current_user_permissions = [c for c in PERMISSION_CODES if current_user.has_permission(c)]
        active_branch = get_active_branch(current_user) if current_user.is_authenticated else None
        active_branch_mode = get_active_branch_mode() if current_user.is_authenticated else "single"

        available_tenants = []
        active_tenant_id = None
        try:
            from utils.tenanting import get_active_tenant_id, is_global_tenant_user
            if current_user.is_authenticated and is_global_tenant_user(current_user):
                active_tenant_id = get_active_tenant_id(current_user)
                from models.tenant import Tenant as TenantModel
                available_tenants = TenantModel.query.filter_by(is_active=True).order_by(TenantModel.id.asc()).all()
        except Exception:
            pass
        app_enums = {
            'permissions': PERMISSIONS,
            'permission_codes': PERMISSION_CODES,
            'customer_types': CUSTOMER_TYPES,
            'payment_statuses': PAYMENT_STATUSES,
            'sale_statuses': SALE_STATUSES,
            'payment_methods': PAYMENT_METHODS,
            'user_roles': USER_ROLES,
        }
        # tenant_* = التينانت (الشركة المستخدمة للنظام). developer_* = الشركة المطورة (مثل أزاد). company_* = alias لـ tenant للتوافق.
        return {
            'format_currency': format_currency,
            'timeago': timeago,
            't': t,
            'is_rtl': is_rtl(),
            'is_rtl_fn': is_rtl,
            'current_language': get_current_language(),
            'get_current_language': get_current_language,
            'get_currency_symbol': get_currency_symbol,
            'number_to_arabic_words': number_to_arabic_words,
            'current_user_permissions': current_user_permissions,
            'app_enums': app_enums,
            'tenant_name_ar': tenant_name_ar,
            'tenant_name': tenant_name,
            'tenant_phone': tenant_phone,
            'tenant_email': tenant_email,
            'tenant_address': tenant_address,
            'tenant_logo_url': tenant_logo_url,
            'tenant_logo_dark_url': tenant_logo_dark_url,
            'tenant_favicon_url': tenant_favicon_url,
            'tenant_default_currency': tenant_default_currency or system_default_currency,
            'tenant_enable_tax': tenant_enable_tax if tenant_enable_tax is not None else system_enable_tax,
            'tenant_default_tax_rate': tenant_default_tax_rate if tenant_default_tax_rate is not None else system_default_tax_rate,
            'company_name': tenant_name or 'ERP System',
            'company_name_ar': tenant_name_ar or 'نظام المحاسبة',
            'company_phone': tenant_phone,
            'company_email': tenant_email,
            'company_address': tenant_address,
            'company_default_currency': tenant_default_currency or system_default_currency,
            'company_enable_tax': tenant_enable_tax if tenant_enable_tax is not None else system_enable_tax,
            'company_default_tax_rate': tenant_default_tax_rate if tenant_default_tax_rate is not None else system_default_tax_rate,
            'system_default_currency': system_default_currency,
            'system_currency_symbol': system_currency_symbol,
            'system_currency_position': system_currency_position,
            'system_decimal_places': system_decimal_places,
            'system_enable_tax': system_enable_tax,
            'system_default_tax_rate': system_default_tax_rate,
            'developer_name_ar': developer_name_ar,
            'developer_name': developer_name,
            'developer_credit': developer_credit,
            'developer_phone': developer_phone,
            'developer_email': developer_email,
            'developer_website': developer_website,
            'developer_whatsapp': developer_whatsapp,
            'developer_whatsapp_link': developer_whatsapp_link,
            'developer_logo': developer_logo,
            'active_branch': active_branch,
            'active_branch_mode': active_branch_mode,
            'available_tenants': available_tenants,
            'active_tenant_id': active_tenant_id,
            'current_year': datetime.now().year,
            'now': datetime.now(),
            'ai_enabled': 'ai' in app.blueprints
        }
        
    @app.before_request
    def before_request():
        g.request_start_time = time.time()
        g.request_id = str(uuid.uuid4())
        
        from utils.i18n import get_current_language, is_rtl
        g.lang_code = get_current_language()
        g.rtl = is_rtl()

        from flask_login import current_user as _cu
        from utils.tenanting import get_active_tenant_id
        from utils.auth_helpers import is_global_owner_user
        g.active_tenant_id = None
        if _cu.is_authenticated:
            g.active_tenant_id = get_active_tenant_id(_cu)
            _bp = request.blueprint or ""
            _skip = {"", "auth", "public", "language", "tenants"}
            if _bp not in _skip and request.endpoint != "static":
                if not is_global_owner_user(_cu) and g.active_tenant_id is None:
                    abort(403)
        
    # Security Headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug and app.config.get('APP_ENV', '').lower() == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Models Import (to ensure they are known to SQLAlchemy)
    from models import User, Customer, ProductCategory
    
    # Initialize Listeners
    try:
        from models.events import register_all_listeners
        with app.app_context():
            register_all_listeners()
    except ImportError:
        app.logger.warning("Event listeners not available")
    
    # Register CLI Commands
    # from cli_commands import register_cli
    # register_cli(app)
    # register_compression_cli(app)
    
    try:
        from cli_commands import register_cli_commands
        register_cli_commands(app)
        app.logger.info("[OK] Enhanced CLI commands registered")
    except ImportError:
        app.logger.info('CLI commands not available - skipping')
    except Exception as e:
        app.logger.warning(f'Enhanced CLI commands not registered: {e}')
    
    app.logger.info('[OK] Application initialized successfully')
    
    return app


if __name__ == '__main__':
    print("DEBUG: Entering main block...", flush=True)
    try:
        app = create_app()
        print("DEBUG: App created successfully", flush=True)
    except Exception as e:
        print(f"DEBUG: Failed to create app: {e}", flush=True)
        raise e
    
    from services.backup_service import BackupService
    BackupService.initialize()
    
    try:
        from services.auto_approval_service import schedule_auto_approval
        schedule_auto_approval(app)
        app.logger.info("Auto-approval service scheduler started")
    except Exception as e:
        app.logger.warning("Auto-approval service failed: %s", e)
    
    import threading
    import time
    import json
    
    def schedule_daily_backup():
        """جدولة النسخ الاحتياطي اليومي"""
        while True:
            try:
                # Use absolute path for settings
                basedir = os.path.abspath(os.path.dirname(__file__))
                settings_path = os.path.join(basedir, 'instance', 'backup_settings.json')
                
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                else:
                    settings = {
                        'enabled': True,
                        'frequency': 'daily',
                        'backup_time': '02:00',
                        'keep_count': 5
                    }
                
                if settings.get('enabled', True):
                    now = datetime.now()
                    backup_time = settings.get('backup_time', '02:00')
                    
                    if settings.get('frequency', 'daily') == 'daily':
                        target_hour, target_minute = map(int, backup_time.split(':'))
                        next_backup = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                        
                        if next_backup <= now:
                            from datetime import timedelta
                            next_backup += timedelta(days=1)
                        
                        wait_seconds = (next_backup - now).total_seconds()
                        
                        app.logger.info("Next automatic backup scheduled at %s", next_backup.strftime('%Y-%m-%d %H:%M:%S'))
                        time.sleep(wait_seconds)
                        
                        with app.app_context():
                            backup = BackupService.auto_backup_daily()
                            if backup:
                                app.logger.info("Automatic backup completed: %s", backup['filename'])
                            else:
                                app.logger.warning("Automatic backup failed")
                    else:
                        time.sleep(86400)
                else:
                    time.sleep(3600)
                    
            except Exception as e:
                app.logger.error("Backup scheduler error: %s", e)
                time.sleep(3600)
    
    try:
        backup_thread = threading.Thread(target=schedule_daily_backup, daemon=True)
        backup_thread.start()
        app.logger.info("Automatic backup scheduler started")
    except:
        pass
    
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug_mode = bool(app.config.get('DEBUG', False))

    def _mask_db_uri(uri: str) -> str:
        if not uri:
            return uri
        try:
            if '://' not in uri or '@' not in uri:
                return uri
            scheme, rest = uri.split('://', 1)
            creds, tail = rest.split('@', 1)
            if ':' not in creds:
                return uri
            user = creds.split(':', 1)[0]
            return f"{scheme}://{user}:***@{tail}"
        except Exception:
            return uri
    
    app.logger.info("Starting UAE-Sale System")
    app.logger.info("Host: %s", host)
    app.logger.info("Port: %s", port)
    app.logger.info("Debug: %s", debug_mode)
    app.logger.info("Database: %s", _mask_db_uri(app.config.get('SQLALCHEMY_DATABASE_URI')))
    app.logger.info("Starting server on http://%s:%s", host, port)
    
    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        use_reloader=False
    )
