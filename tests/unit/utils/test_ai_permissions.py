"""utils/ai_permissions.py — behavioral permission allow/deny matrix.

Covers the AI action → ERP permission mapping with REAL Role/Permission/User
rows so the allow path, the base-permission fallback path, and every deny
path are exercised against the actual ``User.has_permission`` implementation.
"""

from __future__ import annotations

import uuid

import pytest
from flask_login import AnonymousUserMixin, login_user

from utils.ai_permissions import (
    _AI_PERM_MAP,
    get_ai_permission,
    list_permitted_ai_actions,
    user_has_ai_permission,
)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _permission(db_session, code):
    from models import Permission

    perm = Permission.query.filter_by(code=code).first()
    if perm is None:
        perm = Permission(code=code, name=code, name_ar=code, category="ai-test")
        db_session.add(perm)
        db_session.flush()
    return perm


@pytest.fixture
def role_with(db_session):
    """Factory building a real role holding exactly the given permission codes."""

    def _make(codes):
        from models import Role

        suffix = _uid()
        role = Role(name=f"AI Role {suffix}", slug=f"ai-role-{suffix}", is_active=True)
        for code in codes:
            role.permissions.append(_permission(db_session, code))
        db_session.add(role)
        db_session.flush()
        return role

    return _make


@pytest.fixture
def user_in(db_session, sample_tenant):
    """Factory attaching a role to a fresh real user."""

    def _make(role):
        from models import User

        suffix = _uid()
        user = User(
            username=f"ai-u-{suffix}",
            email=f"ai-u-{suffix}@example.com",
            full_name="AI Test User",
            tenant_id=sample_tenant.id,
            role_id=role.id,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.flush()
        return user

    return _make


class TestGetAiPermission:
    def test_mapped_action_returns_ai_specific_code(self):
        assert get_ai_permission("create_customer") == "ai:manage_customers"
        assert get_ai_permission("create_sale") == "ai:manage_sales"

    def test_every_mapping_pair_is_well_formed(self):
        for base, ai_specific in _AI_PERM_MAP.values():
            assert base and not base.startswith("ai:")
            assert ai_specific.startswith("ai:")

    def test_unknown_action_falls_back_to_empty(self):
        assert get_ai_permission("totally_unknown_action") == ""


class TestUserHasAiPermission:
    def test_none_and_unauthenticated_users_are_denied(self, db_session, app):
        with app.test_request_context():
            # Explicit None resolves through to the anonymous current_user.
            assert user_has_ai_permission("create_sale", None) is False

    def test_anonymous_mixin_denied(self):
        assert user_has_ai_permission("create_sale", AnonymousUserMixin()) is False

    def test_owner_bypasses_every_check(self, db_session, sample_owner):
        assert user_has_ai_permission("create_sale", sample_owner) is True
        assert user_has_ai_permission("unknown_action", sample_owner) is True

    def test_ai_specific_permission_allows(self, db_session, role_with, user_in):
        role = role_with(["ai:manage_customers"])
        user = user_in(role)
        assert user_has_ai_permission("create_customer", user) is True
        assert user_has_ai_permission("list_customers", user) is True
        # No sales grant at either level.
        assert user_has_ai_permission("create_sale", user) is False

    def test_base_erp_permission_fallback_allows(self, db_session, role_with, user_in):
        role = role_with(["manage_sales"])
        user = user_in(role)
        assert user_has_ai_permission("create_sale", user) is True
        assert user_has_ai_permission("sales_summary", user) is False

    def test_user_with_no_matching_permission_denied(self, db_session, role_with, user_in):
        role = role_with(["manage_products"])
        user = user_in(role)
        assert user_has_ai_permission("create_sale", user) is False
        assert user_has_ai_permission("receive_payment", user) is False

    def test_unknown_action_type_denied_even_with_grants(self, db_session, role_with, user_in):
        role = role_with(["manage_sales", "manage_customers", "view_reports"])
        user = user_in(role)
        assert user_has_ai_permission("not_a_real_action", user) is False

    def test_view_reports_only_grants_report_actions(self, db_session, role_with, user_in):
        role = role_with(["view_reports"])
        user = user_in(role)
        assert user_has_ai_permission("sales_summary", user) is True
        assert user_has_ai_permission("profit_summary", user) is True
        assert user_has_ai_permission("create_purchase", user) is False

    def test_current_user_path_used_when_user_omitted(self, db_session, app, role_with, user_in):
        role = role_with(["ai:manage_sales"])
        user = user_in(role)
        with app.test_request_context():
            login_user(user)
            assert user_has_ai_permission("create_sale") is True
            assert user_has_ai_permission("add_expense") is False
            assert set(list_permitted_ai_actions()) >= {"create_sale", "list_sales"}

    def test_anonymous_current_user_lists_no_actions(self, db_session, app):
        with app.test_request_context():
            assert list_permitted_ai_actions() == []


class TestListPermittedAiActions:
    def test_owner_gets_every_action(self, db_session, sample_owner):
        permitted = list_permitted_ai_actions(sample_owner)
        assert sorted(permitted) == sorted(_AI_PERM_MAP.keys())

    def test_restricted_user_gets_exact_subset(self, db_session, role_with, user_in):
        role = role_with(["manage_sales", "ai:view_reports"])
        user = user_in(role)
        permitted = set(list_permitted_ai_actions(user))
        assert permitted == {"create_sale", "list_sales", "sales_summary", "profit_summary"}

    def test_permissionless_role_gets_empty_list(self, db_session, role_with, user_in):
        role = role_with([])
        user = user_in(role)
        assert list_permitted_ai_actions(user) == []
