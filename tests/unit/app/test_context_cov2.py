"""Coverage supplement for app/context.py plan-limit filter branches."""

from __future__ import annotations

import pytest
from flask import Flask
from flask_login import LoginManager


@pytest.fixture
def cov2_ctx_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-cov2"
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user_cov2(_user_id):
        return None

    from app.context import register_context_processors

    register_context_processors(app)
    return app


def _plan_limit(cov2_ctx_app):
    return cov2_ctx_app.jinja_env.filters["plan_limit"]


class TestPlanLimitFilterCov2:
    def test_none_returns_dash(self, cov2_ctx_app):
        """Targets app/context.py line 78 (value is None)."""
        assert _plan_limit(cov2_ctx_app)(None) == "—"

    def test_invalid_string_returns_dash(self, cov2_ctx_app):
        """Targets app/context.py lines 81-82 (ValueError branch)."""
        assert _plan_limit(cov2_ctx_app)("not-a-number") == "—"

    def test_invalid_type_returns_dash(self, cov2_ctx_app):
        """Targets app/context.py lines 81-82 (TypeError branch)."""
        assert _plan_limit(cov2_ctx_app)(object()) == "—"

    def test_minus_one_returns_infinity(self, cov2_ctx_app):
        """Targets app/context.py line 84 (v == -1)."""
        filt = _plan_limit(cov2_ctx_app)
        assert filt(-1) == "∞"
        assert filt("-1") == "∞"

    def test_zero_and_negative_return_dash(self, cov2_ctx_app):
        """Targets app/context.py line 86 (v <= 0)."""
        filt = _plan_limit(cov2_ctx_app)
        assert filt(0) == "—"
        assert filt("0") == "—"
        assert filt(-5) == "—"

    def test_positive_returns_value(self, cov2_ctx_app):
        filt = _plan_limit(cov2_ctx_app)
        assert filt(5) == "5"
        assert filt("42") == "42"
