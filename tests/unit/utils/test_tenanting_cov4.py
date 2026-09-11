"""Cov4: tenanting — resolve, active, scope, assert, set/clear, status."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.tenanting as tn


def _user(**kw):
    base = {"is_authenticated": True, "is_owner": False, "tenant_id": 7, "id": 1}
    base.update(kw)
    return SimpleNamespace(**base)


def test_resolve_explicit():
    u = _user()
    assert tn._resolve_user(u) is u  # 24-25


def test_resolve_anon_returns_none():
    import flask_login

    with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False)):
        assert tn._resolve_user(None) is None or tn._resolve_user() is None


def test_is_owner_matrix():
    assert tn.is_platform_owner(_user(is_owner=True, is_authenticated=True)) is True  # 33-36
    assert tn.is_platform_owner(_user(is_owner=False)) is False
    assert tn.is_global_tenant_user(_user(is_owner=True)) is True


def test_get_active_company_locked(app):
    with app.test_request_context("/"):
        assert tn.get_active_tenant_id(_user(is_owner=False, tenant_id=9)) == 9  # 67-69
        assert tn.get_active_tenant_id(_user(is_owner=False, tenant_id=None)) is None


def test_get_active_owner_session(app):
    with app.test_request_context("/"):
        from flask import session

        session["active_tenant_id"] = "42"
        assert tn.get_active_tenant_id(_user(is_owner=True, tenant_id=None)) == 42  # 73-75
        session["active_tenant_id"] = "garbage"
        assert tn.get_active_tenant_id(_user(is_owner=True, tenant_id=8)) == 8  # 76-80


def test_get_active_anon_g(app):
    with app.test_request_context("/"):
        from flask import g

        g.active_tenant_id = 33
        import flask_login

        with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False)):
            assert tn.get_active_tenant_id() == 33  # 57-62


def test_require_aborts(app):
    with app.test_request_context("/"), pytest.raises(Exception):
        with patch.object(tn, "get_active_tenant_id", return_value=None):
            tn.require_active_tenant_id()  # 84-87


def test_apply_scope_branches():
    m = SimpleNamespace(tenant_id=5)
    q = MagicMock()
    q.filter.return_value = "F"
    with patch.object(tn, "get_active_tenant_id", return_value=5):
        assert tn.apply_tenant_scope(q, m) == "F"  # 97-98
    with (
        patch.object(tn, "get_active_tenant_id", return_value=None),
        patch.object(tn, "is_platform_owner", return_value=True),
    ):
        assert tn.apply_tenant_scope(q, m) == "F"  # 99-100
    nomodel = SimpleNamespace()
    with (
        patch.object(tn, "get_active_tenant_id", return_value=None),
        patch.object(tn, "is_platform_owner", return_value=False),
    ):
        assert tn.apply_tenant_scope(q, nomodel) is q  # 101


def test_assert_record_paths(app):
    with app.test_request_context("/"):
        with patch.object(tn, "get_active_tenant_id", return_value=5):
            assert tn.assert_tenant_record(SimpleNamespace(tenant_id=5), or_404=False) is True  # 141
        with (
            patch.object(tn, "get_active_tenant_id", return_value=5),
            patch("utils.tenanting.log_security"),
            pytest.raises(Exception),
        ):
            tn.assert_tenant_record(SimpleNamespace(tenant_id=6, id=1), or_404=True)  # 129-139
        with (
            patch.object(tn, "get_active_tenant_id", return_value=5),
            patch.object(tn, "is_platform_owner", return_value=True),
        ):
            assert tn.assert_tenant_record(SimpleNamespace(tenant_id=None), or_404=False) is True  # 117-119


def test_assign_and_scoped(app):
    rec = SimpleNamespace(tenant_id=9)
    assert tn.assign_tenant_id(rec) is rec  # 159-160
    rec2 = SimpleNamespace(tenant_id=None)
    with patch.object(tn, "require_active_tenant_id", return_value=4):
        assert tn.assign_tenant_id(rec2).tenant_id == 4  # 161-162


def test_without_scope_and_status(app):
    with app.test_request_context("/"):
        with tn.without_tenant_scope():  # 245-255
            from flask import g

            assert g.skip_tenant_scope is True
    assert tn.get_tenant_status(None) == {"ok": True, "suspended": False, "reason": None}  # 262-263
    with patch.object(tn.db.session, "get", return_value=None):
        assert tn.get_tenant_status(99)["ok"] is False  # 266-272
    with patch.object(
        tn.db.session, "get", return_value=SimpleNamespace(is_active=False, is_suspended=False, suspension_reason="x")
    ):
        assert tn.get_tenant_status(1)["suspended"] is True  # 274-280
    with patch.object(tn.db.session, "get", return_value=SimpleNamespace(is_active=True, is_suspended=False)):
        assert tn.get_tenant_status(1)["ok"] is True  # 281


def test_set_clear_active(app):
    with app.test_request_context("/"):
        tn.clear_active_tenant()  # 241-242
        with pytest.raises(ValueError):  # 199-202
            tn.set_active_tenant("abc", user=_user())
        with pytest.raises(ValueError):  # 205-206
            tn.set_active_tenant(1, user=SimpleNamespace(is_authenticated=False, tenant_id=None))
        tn.set_active_tenant(None, user=_user())  # 192-194
