"""Residual-arc coverage for bootstrap/blueprints.py.

Target (branch coverage):
- arc 91->116: AI-fallback ``catch_all`` route when the session already
  contains ``ai_unavailable_notified`` — the ``if not session.get(...)``
  guard is False, so no flash/session write happens and the handler jumps
  straight to the dashboard redirect.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_login import LoginManager

from bootstrap import blueprints as bp_module


@pytest.fixture
def fallback_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(_):
        return MagicMock(is_authenticated=True)

    app.add_url_rule("/dashboard", "main.dashboard", lambda: "ok")
    return app


class TestCatchAllAlreadyNotifiedArc:
    def test_catch_all_skips_flash_when_already_notified(self, fallback_app):
        ai_bp = bp_module._make_ai_fallback("ai unavailable")
        fallback_app.register_blueprint(ai_bp)
        client = fallback_app.test_client()
        with client.session_transaction() as sess:
            sess["ai_unavailable_notified"] = True
        with (
            patch(
                "flask_login.utils._get_user",
                return_value=MagicMock(is_authenticated=True),
            ),
            patch("flask.flash") as flash_mock,
        ):
            resp = client.get("/ai/some-unknown-path", follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"]
        flash_mock.assert_not_called()
        with client.session_transaction() as sess:
            assert sess.get("ai_unavailable_notified") is True

    def test_catch_all_notifies_once_then_skips(self, fallback_app):
        ai_bp = bp_module._make_ai_fallback("ai unavailable")
        fallback_app.register_blueprint(ai_bp)
        with (
            fallback_app.test_client() as client,
            patch(
                "flask_login.utils._get_user",
                return_value=MagicMock(is_authenticated=True),
            ),
        ):
            first = client.get("/ai/first-unknown", follow_redirects=False)
            assert first.status_code == 302
            with client.session_transaction() as sess:
                assert sess.get("ai_unavailable_notified") is True
            with patch("flask.flash") as flash_mock:
                second = client.get("/ai/second-unknown", follow_redirects=False)
            assert second.status_code == 302
            flash_mock.assert_not_called()
