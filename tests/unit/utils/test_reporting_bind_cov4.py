"""Cov4: reporting_bind uncovered arcs — RuntimeError, set/reset, decorator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import utils.reporting_bind as rb
from utils.reporting_bind import reporting_bind, use_reporting_bind


def test_bind_not_configured_falls_back(app):
    with app.test_request_context("/"):
        app.config["SQLALCHEMY_BINDS"] = {}
        with reporting_bind("reporting"):  # lines 57-60
            assert True


def test_bind_is_configured_runtime_error():
    # current_app.config.get raising RuntimeError -> False (lines 32-37)
    fake = MagicMock()
    fake.config.get.side_effect = RuntimeError("no ctx")
    with patch("utils.reporting_bind.current_app", fake):
        assert rb._bind_is_configured("reporting") is False


def test_set_bind_both_branches():
    sess = MagicMock()
    fake_db = MagicMock()
    fake_db.engines = {"reporting": "ENG_R"}
    fake_db.engine = "ENG_D"
    with patch.object(rb, "db", fake_db):
        rb._set_bind(sess, "reporting")  # line 42-43
        assert sess.bind == "ENG_R"
        rb._set_bind(sess, None)  # lines 44-45
        assert sess.bind == "ENG_D"


def test_reporting_bind_configured_restores(app):
    with app.test_request_context("/"):
        app.config["SQLALCHEMY_BINDS"] = {"reporting": "x"}
        sess = MagicMock()
        sess.bind = "ORIG"
        with (
            patch.object(rb, "_get_session", return_value=sess),
            patch.object(rb, "_bind_is_configured", return_value=True),
            patch.object(rb, "_set_bind") as sb,
        ):
            with reporting_bind("reporting"):  # lines 62-66
                sb.assert_called_once()
            assert sess.bind == "ORIG"


def test_reporting_bind_restores_on_exception(app):
    with app.test_request_context("/"):
        app.config["SQLALCHEMY_BINDS"] = {"reporting": "x"}
        sess = MagicMock()
        sess.bind = "ORIG"
        with (
            patch.object(rb, "_get_session", return_value=sess),
            patch.object(rb, "_bind_is_configured", return_value=True),
            patch.object(rb, "_set_bind"),
        ):
            try:
                with reporting_bind():
                    raise ValueError("boom")
            except ValueError:
                pass
            assert sess.bind == "ORIG"  # finally arc line 65-66


def test_use_reporting_bind_decorator(app):
    with app.test_request_context("/"):
        app.config["SQLALCHEMY_BINDS"] = {}

        @use_reporting_bind()
        def _fn(a, b=2):
            return a + b

        assert _fn(1, b=2) == 3  # lines 79-87
        assert _fn.__name__ == "_fn"
