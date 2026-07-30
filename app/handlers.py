"""Error handlers for AZADEXA ERP."""

from flask import jsonify, render_template, request, flash, redirect, url_for, g
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from services.logging_core import LoggingCore
from utils.logger import log_exception


def _wants_json_error_response():
    return (
        request.is_json
        or request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )


def register_error_handlers(app):
    """Register all error handlers on the Flask app."""

    @app.errorhandler(CSRFError)
    def handle_csrf_error(exc):
        LoggingCore.log_error(
            message=str(exc) or "CSRF validation failed",
            category="SECURITY",
            level="WARNING",
            source="app.errorhandler.csrf",
            exception=exc,
        )
        if _wants_json_error_response():
            return (
                jsonify({"success": False, "error": "CSRF token missing or invalid"}),
                400,
            )
        if not current_user.is_authenticated:
            flash("Security token expired. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        return render_template("errors/403.html"), 400

    @app.errorhandler(500)
    def handle_500(exc):
        LoggingCore.log_error(
            message=str(exc) or "Internal Server Error",
            source="app.errorhandler.500",
            exception=exc,
        )
        log_exception(
            str(exc) or "Internal Server Error",
            exception=exc,
            level="ERROR",
            tenant_id=getattr(g, "active_tenant_id", None),
            source="app.errorhandler.500",
            # LoggingCore.log_error above already persists the DB row — the
            # telemetry bridge would double-persist the same real event.
            _bridge=False,
        )
        if app.config.get("DEBUG"):
            raise exc
        return render_template("errors/500.html"), 500

    @app.errorhandler(404)
    def handle_404(exc):
        skip_paths = ["/@vite/", "/node_modules/", "/@react-refresh"]
        skip_log = False
        for path in skip_paths:
            if path in request.path:
                skip_log = True
                break
        if not skip_log:
            LoggingCore.log_error(
                message=f"Page not found: {request.path}",
                category="API",
                level="WARNING",
                source="app.errorhandler.404",
            )
        if app.config.get("DEBUG"):
            raise exc
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def handle_403(exc):
        LoggingCore.log_error(
            message=f"Forbidden access: {request.path}",
            category="SECURITY",
            level="WARNING",
            source="app.errorhandler.403",
        )
        if app.config.get("DEBUG"):
            raise exc
        description = getattr(exc, "description", "") or ""
        if _wants_json_error_response():
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "PERMISSION_DENIED",
                        "message": description or "You do not have permission to perform this action",
                        "status": 403,
                    }
                ),
                403,
            )
        # اعرض سبب الرفض المخصص (مثل رسالة قفل الميزة) دون وصف Werkzeug الافتراضي
        default_desc = (
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server."
        )
        g.denial_reason = description if description and description != default_desc else None
        return render_template("errors/403.html"), 403

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        category = "SECURITY" if exc.code in (401, 429) else "API"
        LoggingCore.log_error(
            message=f"{exc.name}: {request.path}",
            category=category,
            level="WARNING",
            source=f"app.errorhandler.http.{exc.code}",
            exception=exc,
        )
        if _wants_json_error_response():
            body = jsonify(
                {
                    "success": False,
                    "error": exc.name,
                    "status": exc.code,
                }
            )
            # RFC 7231 section 6.5.5: a 405 response must advertise allowed methods
            valid_methods = getattr(exc, "valid_methods", None)
            if valid_methods:
                body.headers["Allow"] = ", ".join(valid_methods)
            return body, exc.code
        return exc

    @app.errorhandler(Exception)
    def handle_generic_exception(exc):
        if isinstance(exc, HTTPException):
            return exc
        # Tenant isolation violation → 403 Forbidden
        if exc.__class__.__name__ == "TenantIsolationError":
            LoggingCore.log_error(
                message=str(exc),
                category="SECURITY",
                level="CRITICAL",
                source="app.errorhandler.tenant_isolation",
                exception=exc,
            )
            if _wants_json_error_response():
                return jsonify({"success": False, "error": str(exc)}), 403
            flash(str(exc), "danger")
            return render_template("errors/403.html"), 403
        category = "DATABASE" if isinstance(exc, SQLAlchemyError) else "BACKEND"
        source = "app.errorhandler.database" if category == "DATABASE" else "app.errorhandler.generic"
        LoggingCore.log_error(
            message=str(exc) or f"{type(exc).__name__} (no message)",
            category=category,
            source=source,
            exception=exc,
        )
        log_exception(
            str(exc) or f"{type(exc).__name__} (no message)",
            exception=exc,
            level="CRITICAL",
            tenant_id=getattr(g, "active_tenant_id", None),
            source=source,
            # LoggingCore.log_error above already persists the DB row — the
            # telemetry bridge would double-persist the same real event.
            _bridge=False,
        )
        if app.config.get("DEBUG"):
            raise exc
        return render_template("errors/500.html"), 500
