"""Error handlers for AZADEXA ERP."""
from flask import jsonify, render_template, request, flash, redirect, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from services.logging_core import LoggingCore


def _wants_json_error_response():
    return (
        request.is_json
        or request.path.startswith('/api/')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
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
            return jsonify({"success": False, "error": "CSRF token missing or invalid"}), 400
        if not current_user.is_authenticated:
            flash("Security token expired. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        return render_template("errors/403.html"), 400

    @app.errorhandler(500)
    def handle_500(exc):
        LoggingCore.log_error(
            message=str(exc) or "Internal Server Error",
            category="BACKEND",
            level="ERROR",
            source="app.errorhandler.500",
            exception=exc,
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
            return jsonify({
                "success": False,
                "error": exc.name,
                "status": exc.code,
            }), exc.code
        return exc

    @app.errorhandler(Exception)
    def handle_generic_exception(exc):
        if isinstance(exc, HTTPException):
            return exc
        # Tenant isolation violation → 403 Forbidden
        if exc.__class__.__name__ == 'TenantIsolationError':
            from utils.tenant_orm import TenantIsolationError
            LoggingCore.log_error(
                message=str(exc),
                category="SECURITY",
                level="CRITICAL",
                source="app.errorhandler.tenant_isolation",
                exception=exc,
            )
            if _wants_json_error_response():
                return jsonify({"success": False, "error": str(exc)}), 403
            flash(str(exc), 'danger')
            return render_template("errors/403.html"), 403
        category = "DATABASE" if isinstance(exc, SQLAlchemyError) else "BACKEND"
        source = "app.errorhandler.database" if category == "DATABASE" else "app.errorhandler.generic"
        LoggingCore.log_error(
            message=str(exc) or f"{type(exc).__name__} (no message)",
            category=category,
            level="ERROR",
            source=source,
            exception=exc,
        )
        if app.config.get("DEBUG"):
            raise exc
        return render_template("errors/500.html"), 500
