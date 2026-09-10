"""Coverage supplement for app/handlers.py TenantIsolationError HTML branch."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from app.handlers import register_error_handlers


@pytest.fixture
def cov2_handlers_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-cov2"
    app.config["TESTING"] = True
    app.config["DEBUG"] = False
    register_error_handlers(app)

    @app.route("/page")
    def cov2_page():
        return "ok"

    return app


class TestTenantIsolationHtmlCov2:
    def test_html_flash_and_render_403(self, cov2_handlers_app):
        """Targets app/handlers.py lines 171-172 (non-JSON TenantIsolationError)."""
        from utils.tenant_orm import TenantIsolationError

        handler = cov2_handlers_app.error_handler_spec[None][None][Exception]
        with (
            patch("app.handlers.LoggingCore.log_error"),
            patch("app.handlers.flash") as flash_mock,
            patch("app.handlers.render_template", return_value="forbidden") as render_mock,
            cov2_handlers_app.test_request_context("/page"),
        ):
            result = handler(TenantIsolationError("cross-tenant denied"))
        flash_mock.assert_called_once_with("cross-tenant denied", "danger")
        render_mock.assert_called_once_with("errors/403.html")
        body, status = result
        assert status == 403
        assert body == "forbidden"
