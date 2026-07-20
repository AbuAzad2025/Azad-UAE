"""Flask application factory for AZADEXA ERP."""

import os
import uuid
import time

from flask import (
    Flask,
    request,
    g,
    redirect,
    url_for,
    flash,
    abort,
    send_from_directory,
)

import config
from config import Config, ensure_runtime_dirs, assert_production_sanity
from extensions import db, init_extensions
from services.logging_core import LoggingCore
from typing import cast, Any
from werkzeug.middleware.proxy_fix import ProxyFix
from utils import bootstrap_keys

from app.handlers import register_error_handlers
from app.context import register_context_processors
from app.integrity import run_system_integrity_check

try:
    from flask_compress import Compress  # noqa: F401

    COMPRESS_AVAILABLE = True
except ImportError:
    COMPRESS_AVAILABLE = False


def create_app(config_class=Config) -> Flask:
    config._init_env()
    # Flask app is inside app/ package; templates/static live at project root
    project_root: str = os.path.abspath(os.path.join(str(os.path.dirname(__file__)), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
    )
    app.config.from_object(config_class)

    # Bootstrap SECRET_KEY and CARD_ENCRYPTION_KEY outside Config class
    bootstrap_keys.bootstrap_keys(app, config.instance_dir)

    # Ensure runtime directories exist
    ensure_runtime_dirs(config_class)

    # Verify production sanity (Database check)
    assert_production_sanity(config_class)

    # Dev mode: auto-generate owner password if empty
    if app.config.get("DEBUG") or app.config.get("APP_ENV", "production") != "production":
        if not os.environ.get("OWNER_PASSWORD"):
            import secrets
            import string

            _generated = "".join(secrets.choice(string.ascii_letters + string.digits + "@$!%*?&") for _ in range(20))
            app.config["OWNER_PASSWORD"] = _generated
            os.environ["OWNER_PASSWORD"] = _generated
            print(f"\r\n{'=' * 60}\r\n[DEV MODE] Auto-generated OWNER_PASSWORD: {_generated}\r\n{'=' * 60}\r\n")

    init_extensions(app)

    from extensions import login_manager
    from models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id), execution_options={"skip_tenant_scope": True})

    @login_manager.unauthorized_handler
    def _handle_unauthorized():
        if request.path.startswith("/owner/"):
            abort(404)
        flash("الرجاء تسجيل الدخول للوصول لهذه الصفحة", "warning")
        return redirect(url_for("auth.login"))

    LoggingCore.setup(app)
    LoggingCore.schedule_cleanup(app)

    # System integrity check
    if not os.environ.get("SKIP_SYSTEM_INTEGRITY"):
        print("Running system integrity check...")
        run_system_integrity_check(app)
        print("System integrity check passed")

    # Default tenant maintenance check at startup
    if not os.environ.get("SKIP_SYSTEM_INTEGRITY"):
        run_default_tenant_maintenance_api = None
        try:
            from services.maintenance_service import run_default_tenant_maintenance_api  # type: ignore[assignment]
        except ImportError:
            pass

        if run_default_tenant_maintenance_api is not None:
            with app.app_context():
                result = run_default_tenant_maintenance_api()
                if result.get("action_needed"):
                    app.logger.info(f"[OK] Default tenant maintenance completed: {result}")
                else:
                    app.logger.info("[OK] Default tenant maintenance check passed - no action needed")
        else:
            app.logger.info("Default tenant maintenance service not available - skipping")

    # Proxy Fix for Nginx/Cloudflare
    cast(Any, app).wsgi_app = ProxyFix(app.wsgi_app, x_host=1, x_prefix=1)

    from bootstrap.blueprints import register_blueprints

    register_blueprints(app)

    @app.before_request
    def storefront_custom_domain_redirect():
        """Route custom domain / subdomain to the tenant storefront catalog."""
        path = request.path or "/"
        if path.startswith(
            (
                "/.well-known/",
                "/favicon.ico",
                "/s/",
                "/static/",
                "/auth/",
                "/store/",
                "/api/",
                "/owner/",
                "/admin",
            )
        ):
            return None
        from services.store_service import StoreService

        store = StoreService.get_store_by_host(request.host)
        if store and StoreService.is_store_publicly_available(store):
            from flask import redirect, url_for

            return redirect(url_for("shop.catalog", slug=store.store_slug))
        return None

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            str(app.static_folder),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_metadata():
        return "", 204

    # Register error handlers
    register_error_handlers(app)

    # Register context processors
    register_context_processors(app)

    @app.before_request
    def before_request():
        g.request_start_time = time.time()
        from services.logging_core import LoggingCore

        LoggingCore.set_trace_id()
        if not hasattr(g, "request_id") or not g.request_id:
            g.request_id = str(uuid.uuid4())

        from utils.i18n import get_current_language, is_rtl

        g.lang_code = get_current_language()
        g.rtl = is_rtl()

        from flask_login import current_user as _cu
        from utils.tenanting import get_active_tenant_id, get_tenant_status
        from utils.auth_helpers import is_global_owner_user

        g.active_tenant_id = None
        if _cu.is_authenticated:
            g.active_tenant_id = get_active_tenant_id(_cu)
            _bp = request.blueprint or ""
            _skip = {"", "auth", "public", "language", "tenants", "owner"}
            if _bp not in _skip and request.endpoint != "static":
                if not is_global_owner_user(_cu) and g.active_tenant_id is None:
                    abort(403)
                if g.active_tenant_id is not None and not is_global_owner_user(_cu):
                    status = get_tenant_status(g.active_tenant_id)
                    if not status["ok"]:
                        from flask import render_template

                        return (
                            render_template(
                                "public/tenant_suspended.html",
                                tenant=status.get("tenant"),
                                reason=status.get("reason") or "Tenant suspended",
                            ),
                            503,
                        )

                if g.active_tenant_id is not None and not is_global_owner_user(_cu) and _bp not in _skip:
                    from flask import render_template as _rt
                    from models.tenant import Tenant as _Tn

                    _tenant = db.session.get(_Tn, int(g.active_tenant_id))
                    if _tenant and not _tenant.is_lifetime and not _tenant.is_subscription_active():
                        return (
                            _rt(
                                "public/subscription_expired.html",
                                tenant=_tenant,
                            ),
                            402,
                        )

                if g.active_tenant_id is not None and not is_global_owner_user(_cu):
                    from services.saas_provisioning_service import (
                        SaaSProvisioningService,
                    )
                    from models.tenant import Tenant as _Tn

                    _t = db.session.get(_Tn, int(g.active_tenant_id)) if g.active_tenant_id else None
                    if _t and SaaSProvisioningService.is_demo_tenant(_t) and _bp in ("owner", "payment_vault"):
                        abort(404)

        return None

    # Security Headers + Request ID
    @app.after_request
    def add_security_headers(response):
        if "charset" not in response.content_type and response.content_type.startswith("text/"):
            response.headers["Content-Type"] = response.content_type + "; charset=utf-8"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if hasattr(g, "request_id") and g.request_id:
            response.headers["X-Request-Id"] = g.request_id
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug and app.config.get("APP_ENV", "").lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob:; "
            "media-src 'self' data: blob:; "
            "connect-src 'self' wss: https://cdn.jsdelivr.net; "
            "frame-ancestors 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
        )
        response.headers["Content-Security-Policy"] = csp
        return response

    register_all_listeners = None
    try:
        from models.events import register_all_listeners  # type: ignore[assignment]
    except ImportError:
        pass

    if register_all_listeners is not None:
        try:
            with app.app_context():
                register_all_listeners()
        except ImportError:
            app.logger.warning("Event listeners not available")
    else:
        app.logger.warning("Event listeners not available")

    # Tenant ORM scoping (after all models are imported so registry is populated)
    # SECURITY-CRITICAL: this listener is the backbone of the multi-tenant
    # isolation model. If it fails to register, tenant auto-scoping is silently
    # DISABLED and any tenant could read/write another tenant's data. We must
    # NOT continue serving as if nothing happened.
    try:
        from utils.tenant_orm import register_tenant_orm_scoping

        register_tenant_orm_scoping(app)
        app.config["TENANT_ISOLATION_ACTIVE"] = True
    except Exception as exc:  # pragma: no cover - defensive backstop
        app.config["TENANT_ISOLATION_ACTIVE"] = False
        app.logger.critical(
            "[CRITICAL] Tenant ORM scoping FAILED to register: %s — "
            "multi-tenant isolation is DISABLED. Refusing to serve tenant "
            "traffic until this is resolved.",
            exc,
        )

        @app.before_request
        def _block_requests_without_isolation():
            from flask import abort

            # Allow owner/platform blueprints and static so the operator can
            # still reach health/diagnostics, but block tenant-data blueprints.
            from utils.tenant_orm import TENANT_DATA_BLUEPRINTS

            bp = (request.blueprint or "") if request else ""
            if bp in TENANT_DATA_BLUEPRINTS:
                abort(503, description="Tenant isolation unavailable")

    # Register CLI Commands
    register_cli_commands = None
    try:
        from cli_commands import register_cli_commands  # type: ignore[assignment]
    except ImportError:
        pass

    if register_cli_commands is not None:
        try:
            register_cli_commands(app)
            app.logger.info("[OK] Enhanced CLI commands registered")
        except ImportError:
            app.logger.info("CLI commands not available - skipping")
        except Exception as e:
            app.logger.warning(f"CLI commands not registered: {e}")
    else:
        app.logger.info("CLI commands not available - skipping")

    app.logger.info("[OK] Application initialized successfully")

    return app
