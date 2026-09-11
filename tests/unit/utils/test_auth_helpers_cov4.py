"""Cov4: auth_helpers — levels, admin/owner checks, enforce tenant."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from models.enums import RoleEnum
from utils.auth_helpers import (
    enforce_company_user_tenant,
    is_admin_surface_user,
    is_global_owner_user,
    role_level_for,
    role_level_for_user,
    user_may_have_null_tenant,
)


def test_role_levels():
    assert role_level_for("owner") >= 0  # 13
    assert role_level_for_user(None) == 0  # 19-20
    assert role_level_for_user(SimpleNamespace(is_owner=True)) >= 100  # 20-21
    assert role_level_for_user(SimpleNamespace(is_owner=False, role=SimpleNamespace(slug="seller"))) >= 0  # 22-24


def test_admin_surface():
    assert is_admin_surface_user(None) is False  # 31-32
    assert is_admin_surface_user(SimpleNamespace(is_owner=True)) is True  # 34-35
    assert is_admin_surface_user(SimpleNamespace(is_owner=False, role=None)) is False  # 37-38
    r = SimpleNamespace(slug=RoleEnum.SUPER_ADMIN.value, name="x")
    assert is_admin_surface_user(SimpleNamespace(is_owner=False, role=r)) is True  # 41
    r2 = SimpleNamespace(slug="x", name=RoleEnum.SUPER_ADMIN.name)
    assert is_admin_surface_user(SimpleNamespace(is_owner=False, role=r2)) is True


def test_global_owner():
    assert is_global_owner_user(None) is False  # 50-51
    assert is_global_owner_user(SimpleNamespace(is_owner=True, tenant_id=None)) is True  # 52-55
    assert is_global_owner_user(SimpleNamespace(is_owner=True, tenant_id=5, role=None)) is False
    assert is_global_owner_user(SimpleNamespace(is_owner=False, role=SimpleNamespace(slug="developer"))) is True  # 58


def test_may_null():
    assert user_may_have_null_tenant(is_owner=True) is True  # 63-64
    assert user_may_have_null_tenant(role=SimpleNamespace(slug="developer")) is True  # 66
    assert user_may_have_null_tenant(role=SimpleNamespace(slug="seller")) is False


def test_enforce_passthroughs():
    u = SimpleNamespace(is_owner=True, tenant_id=None, role=None, branch_id=None)
    assert enforce_company_user_tenant(u) is u  # 76-77
    u2 = SimpleNamespace(is_owner=False, tenant_id=5, role=SimpleNamespace(slug="seller"), branch_id=None)
    assert enforce_company_user_tenant(u2) is u2  # 78-79


def test_enforce_branch_resolve():
    u = SimpleNamespace(is_owner=False, tenant_id=None, role=SimpleNamespace(slug="seller"), branch_id=11)
    with patch("utils.auth_helpers.db") as mdb:
        mdb.session.get.return_value = SimpleNamespace(tenant_id=77)
        assert enforce_company_user_tenant(u).tenant_id == 77  # 81-87


def test_enforce_assign_and_raise():
    u = SimpleNamespace(is_owner=False, tenant_id=None, role=SimpleNamespace(slug="seller"), branch_id=None)
    with patch("utils.tenanting.assign_tenant_id", side_effect=lambda r: setattr(r, "tenant_id", 9)):
        assert enforce_company_user_tenant(u).tenant_id == 9  # 88-91
    u2 = SimpleNamespace(is_owner=False, tenant_id=None, role=SimpleNamespace(slug="seller"), branch_id=None)
    with patch("utils.tenanting.assign_tenant_id", side_effect=lambda r: None):
        try:
            enforce_company_user_tenant(u2)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass  # 91-92
