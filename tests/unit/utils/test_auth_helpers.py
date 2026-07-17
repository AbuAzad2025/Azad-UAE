from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from utils.auth_helpers import (
    enforce_company_user_tenant,
    is_admin_surface_user,
    is_global_owner_user,
    role_level_for,
    role_level_for_user,
    user_may_have_null_tenant,
)


class TestRoleHelpers:
    def test_role_level_for_unknown(self):
        assert role_level_for("unknown") == 0

    def test_role_level_for_user_none(self):
        assert role_level_for_user(None) == 0

    def test_role_level_for_owner(self):
        user = MagicMock(is_owner=True, role=None)
        assert role_level_for_user(user) >= 100

    def test_is_admin_surface_owner(self):
        assert is_admin_surface_user(MagicMock(is_owner=True)) is True

    def test_is_admin_surface_super_admin(self):
        role = MagicMock(slug="super_admin")
        assert is_admin_surface_user(MagicMock(is_owner=False, role=role)) is True

    def test_is_admin_surface_regular(self):
        role = MagicMock(slug="accountant")
        assert is_admin_surface_user(MagicMock(is_owner=False, role=role)) is False

    def test_is_global_owner_platform_owner(self):
        user = MagicMock(is_owner=True, tenant_id=None)
        assert is_global_owner_user(user) is True

    def test_is_global_owner_developer_role(self):
        role = MagicMock(slug="developer")
        assert is_global_owner_user(MagicMock(is_owner=False, role=role)) is True

    def test_user_may_have_null_tenant(self):
        assert user_may_have_null_tenant(is_owner=True) is True
        assert (
            user_may_have_null_tenant(is_owner=False, role=MagicMock(slug="developer"))
            is True
        )
        assert (
            user_may_have_null_tenant(is_owner=False, role=MagicMock(slug="manager"))
            is False
        )

    def test_role_level_for_user_with_role(self):
        role = MagicMock(slug="manager")
        user = MagicMock(is_owner=False, role=role)
        assert role_level_for_user(user) >= 0

    def test_is_admin_surface_none_user(self):
        assert is_admin_surface_user(None) is False

    def test_is_global_owner_none_user(self):
        assert is_global_owner_user(None) is False


class TestEnforceCompanyUserTenant:
    def test_owner_skips_enforcement(self):
        user = MagicMock(is_owner=True, tenant_id=None, role=None)
        assert enforce_company_user_tenant(user) is user

    def test_existing_tenant_id(self):
        user = MagicMock(is_owner=False, tenant_id=5, role=MagicMock(slug="manager"))
        assert enforce_company_user_tenant(user).tenant_id == 5

    def test_tenant_from_branch(self):
        user = MagicMock(
            is_owner=False, tenant_id=None, branch_id=3, role=MagicMock(slug="manager")
        )
        branch = MagicMock(tenant_id=9)
        with patch("utils.auth_helpers.db") as mock_db:
            mock_db.session.get.return_value = branch
            result = enforce_company_user_tenant(user)
        assert result.tenant_id == 9

    @staticmethod
    def _assign_tenant_id(u):
        u.tenant_id = 2
        return u

    def test_assign_tenant_id_fallback(self):
        user = MagicMock(
            is_owner=False,
            tenant_id=None,
            branch_id=None,
            role=MagicMock(slug="manager"),
        )
        with patch(
            "utils.tenanting.assign_tenant_id",
            side_effect=self._assign_tenant_id,
        ):
            result = enforce_company_user_tenant(user)
        assert result.tenant_id == 2

    def test_raises_when_no_tenant(self):
        user = MagicMock(
            is_owner=False,
            tenant_id=None,
            branch_id=None,
            role=MagicMock(slug="manager"),
        )
        with patch("utils.tenanting.assign_tenant_id", side_effect=lambda u: u):
            with pytest.raises(ValueError, match="tenant_id"):
                enforce_company_user_tenant(user)
