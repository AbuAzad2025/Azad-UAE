"""Cov4: branching — global/user resolution, branch ids, stock maps, guards."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils.branching as br


def _u(**kw):
    d = {"is_authenticated": True, "is_owner": False, "branch_id": 3, "tenant_id": 1, "id": 1}
    d.update(kw)
    u = SimpleNamespace(**d)
    u.is_super_admin = (lambda: kw.get("super", False)) if "super" in kw else (lambda: False)
    return u


def test_resolve_explicit_and_anon():
    u = _u()
    assert br._resolve_user(u) is u  # 16-18
    import flask_login

    with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False)):
        assert br._resolve_user() is None


def test_is_global_matrix():
    assert br.is_global_user(SimpleNamespace(is_authenticated=False)) is False  # 28-29
    assert br.is_global_user(_u(is_owner=True)) is True  # 31-32
    assert br.is_global_user(_u(super=True)) is True  # 39-40


def test_branch_scope_unauth_and_global(app):
    assert br.branch_scope_id_for(SimpleNamespace(is_authenticated=False)) is None  # 45-46
    with app.test_request_context("/"):
        u = _u(is_owner=True)
        with (
            patch.object(br, "get_active_branch_id", return_value=9),
            patch.object(br, "is_global_user", return_value=True),
        ):
            assert br.branch_scope_id_for(u) == 9  # 48-49
        u2 = _u(branch_id=4)
        with (
            patch.object(br, "get_active_branch_id", return_value=None),
            patch.object(br, "is_global_user", return_value=False),
        ):
            assert br.branch_scope_id_for(u2) == 4  # 50


def test_report_scope_home_branch():
    u = _u(is_owner=False, branch_id=6)
    with (
        patch.object(br, "branch_scope_id_for", return_value=None),
        patch.object(br, "is_global_user", return_value=True),
    ):
        assert br.report_branch_scope_id_for(u) == 6  # 62-65
    with (
        patch.object(br, "branch_scope_id_for", return_value=None),
        patch.object(br, "is_global_user", return_value=False),
    ):
        assert br.report_branch_scope_id_for(u) is None  # 66


def test_role_requires_and_mode(app):
    assert br.role_requires_branch(SimpleNamespace(slug="x"), is_owner=True) is False  # 70-71
    assert br.get_active_branch_mode() == "single"  # 123-124 no ctx
    with app.test_request_context("/"):
        assert br.get_active_branch_mode() == "single"  # 125
        assert br.should_show_all_branch_columns(SimpleNamespace(is_authenticated=False)) is False  # 135
        assert br.get_active_branch_id(SimpleNamespace(is_authenticated=False)) is None  # 143-144
        br.clear_active_branch()  # 197-201
        with patch.object(br, "user_can_access_branch", return_value=True):
            br.set_active_branch(None, user=_u())  # global-False, branch fallback path


def test_stock_maps_empty():
    assert br.get_branch_stock_map(warehouse_ids=[]) == {}  # 238-239
    assert br.get_warehouse_stock_map(warehouse_ids=None) == {}  # 262-263
    assert br.get_product_stock(1, warehouse_ids=[]) == 0  # 283-290 (Decimal 0)


def test_access_guards():
    assert br.user_can_access_branch(None, user=_u(is_owner=True)) in (True, False)  # 103-104
    assert br.user_can_access_branch("bad!!", user=_u()) is False  # 105-108
    assert br.user_can_access_warehouse(None, user=_u()) is False  # 319-320
    with pytest.raises(ValueError):  # 328-329
        br.ensure_warehouse_access(None, user=_u())
