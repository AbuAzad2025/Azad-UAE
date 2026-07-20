"""User, Role, Permission model — password, permissions, serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock


class TestPermissionModel:
    def test_repr_and_to_dict(self):
        from models.user import Permission

        perm = Permission(code="manage_sales", name="Sales", name_ar="مبيعات", category="sales")
        assert "manage_sales" in repr(perm)
        data = perm.to_dict()
        assert data["code"] == "manage_sales"
        assert data["category"] == "sales"


class TestRoleModel:
    def test_repr_has_permission_and_to_dict(self):
        from models.user import Role, Permission

        role = Role(name="Manager", slug="manager")
        p1 = Permission(code="view_reports")
        p2 = Permission(code="edit_products")
        role.permissions = [p1, p2]
        assert "Manager" in repr(role)
        assert role.has_permission("view_reports") is True
        assert role.has_permission("delete_all") is False
        data = role.to_dict()
        assert set(data["permissions"]) == {"view_reports", "edit_products"}


class TestUserModel:
    @staticmethod
    def _user(**kwargs):
        from models.user import User, Role

        user = User(username="alice", email="alice@test.com")
        user.id = 1
        user.full_name = "Alice"
        user.full_name_ar = "أليس"
        user.is_active = True
        user.is_owner = kwargs.get("is_owner", False)
        user.email_verified = True
        user.login_attempts = 0
        user.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        slug = kwargs.get("role_slug", "seller")
        user.role = Role(name=slug.title(), slug=slug, permissions=[])
        if kwargs.get("permissions"):
            user.role.permissions = [MagicMock(code=c) for c in kwargs["permissions"]]
        return user

    def test_repr(self):
        assert "alice" in repr(self._user())

    def test_password_hash_roundtrip(self):
        user = self._user()
        user.set_password("Secret123!")
        assert user.check_password("Secret123!") is True
        assert user.check_password("wrong") is False

    def test_role_checks(self):
        assert self._user(role_slug="super_admin").is_super_admin() is True
        assert self._user(role_slug="manager").is_manager() is True
        assert self._user(role_slug="seller").is_seller() is True
        owner = self._user(is_owner=True, role_slug="seller")
        assert owner.is_admin() is True
        assert owner.has_permission("anything") is True

    def test_has_permission_via_role(self):
        user = self._user(permissions=["manage_inventory"])
        assert user.has_permission("manage_inventory") is True
        assert user.has_permission("manage_billing") is False

    def test_can_see_costs_and_discount_rules(self):
        assert self._user(role_slug="manager").can_see_costs() is True
        seller = self._user(role_slug="seller")
        assert seller.can_apply_discount() is False
        assert seller.can_edit_price() is False
        owner = self._user(is_owner=True)
        assert owner.can_apply_discount() is True

    def test_get_display_name(self):
        user = self._user()
        assert user.get_display_name("ar") == "أليس"
        user.full_name_ar = None
        assert user.get_display_name("ar") == "Alice"

    def test_to_dict_masks_owner_from_other_viewer(self):
        owner = self._user(is_owner=True)
        owner.id = 99
        viewer = self._user()
        viewer.id = 1
        data = owner.to_dict(viewer=viewer)
        assert data["username"] == "***"
        assert data["email"] == "***@***.***"

    def test_to_dict_owner_viewing_self_not_masked(self):
        owner = self._user(is_owner=True)
        data = owner.to_dict(viewer=owner)
        assert data["username"] == "alice"

    def test_can_edit_price_owner(self):
        owner = self._user(is_owner=True)
        assert owner.can_edit_price() is True

        user = self._user()
        user.last_login = datetime(2025, 6, 1, tzinfo=timezone.utc)
        data = user.to_dict(viewer=user, include_sensitive=True)
        assert data["email_verified"] is True
        assert "last_login" in data
