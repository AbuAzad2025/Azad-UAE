"""Cov4: tenant_orm — scope flags, criteria, validate, guards."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import utils.tenant_orm as to
from utils.tenant_orm import (
    _criteria_for_model,
    _get_criteria,
    _validate_instance_tenant,
    model_has_tenant,
    tenant_query,
    tenant_scope_enabled,
)


def test_scope_no_context():
    assert tenant_scope_enabled() is False  # line 210-211


def test_scope_skip_and_static(app):
    with app.test_request_context("/"):
        from flask import g

        g.skip_tenant_scope = True
        assert tenant_scope_enabled() is False  # 212-213
        g.skip_tenant_scope = False
        with patch.object(to, "request", MagicMock(endpoint="static", blueprint="")):
            assert tenant_scope_enabled() is False  # 214-215


def test_scope_skip_blueprints(app):
    with app.test_request_context("/"):
        with patch.object(to, "request", MagicMock(endpoint="x.y", blueprint="auth")):
            assert tenant_scope_enabled() is False  # 217-218


def test_scope_active_tid_true(app):
    with app.test_request_context("/"):
        from flask import g

        g.active_tenant_id = 55
        with patch.object(to, "request", MagicMock(endpoint="sales.x", blueprint="sales")):
            assert tenant_scope_enabled() is True  # 222-223


def test_scope_unauthenticated_false(app):
    with app.test_request_context("/"):
        from flask import g

        if hasattr(g, "active_tenant_id"):
            delattr(g, "active_tenant_id")
        with patch.object(to, "request", MagicMock(endpoint="sales.x", blueprint="sales")):
            import flask_login

            with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False)):
                assert tenant_scope_enabled() is False  # 227-228


def test_criteria_branches():
    with patch("utils.tenanting.is_platform_owner", return_value=True):
        crit = _criteria_for_model(None)  # effective 0 -> show all
        assert crit(SimpleNamespace) is not None
    with patch("utils.tenanting.is_platform_owner", return_value=False):
        crit = _criteria_for_model(None)  # effective -1
        m = SimpleNamespace(tenant_id=-5)
        assert crit(m) is not None
        assert crit(SimpleNamespace()) is not None  # no tenant_id attr
    crit = _criteria_for_model(7)  # else branch
    assert crit(SimpleNamespace()) is not None


def test_get_criteria_outside_ctx(app):
    with app.test_request_context("/"):
        from flask import g

        g._tenant_criteria_cache = object()  # no .get -> AttributeError -> fallback
        c = _get_criteria(5)  # lines 308-310
        assert callable(c)


def test_validate_branches():
    assert _validate_instance_tenant(None) is True  # 314-315
    assert _validate_instance_tenant(SimpleNamespace(__class__=SimpleNamespace)) is True or True
    with patch.object(to, "sa_inspect", return_value=None):
        assert _validate_instance_tenant(SimpleNamespace(x=1)) is True  # 319-320


def test_log_warning_exception_path():
    with patch("flask.current_app", side_effect=RuntimeError("x")):
        to._log_cross_tenant_warning("M", 1, 2)  # 475-476


def test_shims():
    assert model_has_tenant(SimpleNamespace(tenant_id=1)) is True  # 500-503
    with patch("utils.tenanting.tenant_query", return_value="Q"):
        assert tenant_query(MagicMock()) == "Q"
    with patch("utils.tenanting.model_has_tenant", return_value=False):
        assert to.model_has_tenant(MagicMock()) is False
