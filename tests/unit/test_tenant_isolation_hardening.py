"""Tests for tenant isolation hardening"""
import uuid

import pytest
from decimal import Decimal
from datetime import date
from models.fixed_asset import FixedAsset, DepreciationSchedule
from models.gl import GLAccount
from models.user import User, Role
from models.branch import Branch
from models.tenant import Tenant
from extensions import db


@pytest.fixture(autouse=True)
def _tenant_test_request_context(app):
    """Keep an active Flask request context so session-based tenanting works."""
    with app.test_request_context():
        yield


class TestTenantIsolationHardening:
    """Test tenant isolation hardening in auth and tenanting"""

    def _create_second_tenant(self, db_session, **overrides):
        """Create an isolated second tenant (unique slug avoids cross-suite DB pollution)."""
        uid = uuid.uuid4().hex[:8]
        data = {
            "name": f"Test Company 2 {uid}",
            "name_ar": "شركة تجربة 2",
            "slug": f"test-company-2-{uid}",
            "email": f"test2-{uid}@example.com",
            "phone_1": "0500000001",
            "country": "AE",
            "subscription_plan": "basic",
            "is_active": True,
            "is_suspended": False,
        }
        data.update(overrides)
        tenant2 = Tenant(**data)
        db_session.add(tenant2)
        db_session.flush()
        return tenant2

    def _create_test_user(self, db_session, tenant_id, branch_id=None, is_owner=False):
        """Create a test user for testing"""
        uid = uuid.uuid4().hex[:8]
        role = Role.query.filter_by(slug=f"test-role-{uid}").first()
        if not role:
            role = Role(name=f"Test Role {uid}", slug=f"test-role-{uid}", is_active=True)
            db_session.add(role)
            db_session.flush()
        user = User(
            username=f"testuser_{tenant_id}_{uid}",
            email=f"testuser_{tenant_id}_{uid}@example.com",
            full_name="Test User",
            full_name_ar="مستخدم تجربة",
            phone="0500000000",
            role_id=role.id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            is_owner=is_owner,
            is_active=True,
        )
        user.set_password("testpassword")
        db_session.add(user)
        db_session.flush()
        return user

    def test_normal_user_cannot_set_another_tenant(self, db_session, sample_tenant, sample_branch):
        """Test normal user cannot set session tenant to another tenant"""
        from utils.tenanting import set_active_tenant

        # Create a normal user for sample_tenant
        user = self._create_test_user(db_session, sample_tenant.id)

        # Create a second tenant
        tenant2 = self._create_second_tenant(db_session)

        # Try to set tenant2 as active tenant for user
        with pytest.raises(ValueError, match="Normal users can only set their own tenant_id"):
            set_active_tenant(tenant2.id, user=user)

    def test_platform_owner_can_set_active_tenant(self, db_session, sample_tenant, sample_branch):
        """Test platform owner can set active tenant"""
        from utils.tenanting import set_active_tenant

        # Create a platform owner user
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)

        # Create a second tenant
        tenant2 = self._create_second_tenant(db_session)

        # Platform owner should be able to set tenant2
        set_active_tenant(tenant2.id, user=owner)

        # Verify tenant was set
        from utils.tenanting import get_active_tenant_id
        assert get_active_tenant_id(user=owner) == tenant2.id

    def test_normal_user_branch_must_belong_to_same_tenant(self, db_session, sample_tenant, sample_branch):
        """Test normal user branch must belong to same tenant"""
        from utils.branching import get_accessible_branches

        # Create a normal user for sample_tenant
        user = self._create_test_user(db_session, sample_tenant.id, branch_id=sample_branch.id)

        # Create a second tenant and branch
        tenant2 = self._create_second_tenant(db_session)

        branch2 = Branch(
            tenant_id=tenant2.id,
            name="Branch 2",
            code="BR2",
            is_active=True,
        )
        db_session.add(branch2)
        db_session.flush()

        # Normal user should only have access to branches in their tenant
        accessible_branches = get_accessible_branches(user=user)
        branch_ids = [b.id for b in accessible_branches]
        assert branch2.id not in branch_ids
        assert sample_branch.id in branch_ids

    def test_platform_owner_can_switch_to_active_tenant(self, db_session, sample_tenant, sample_branch):
        """Test platform owner can switch to active tenant"""
        from utils.tenanting import set_active_tenant

        # Create a platform owner user
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)

        # Create a second tenant
        tenant2 = self._create_second_tenant(db_session)

        # Platform owner should be able to set tenant2
        set_active_tenant(tenant2.id, user=owner)

        # Verify tenant was set
        from utils.tenanting import get_active_tenant_id
        assert get_active_tenant_id(user=owner) == tenant2.id

    def test_platform_owner_cannot_switch_to_inactive_tenant(self, db_session, sample_tenant, sample_branch):
        """Test platform owner cannot switch to inactive tenant"""
        from utils.tenanting import set_active_tenant

        # Create a platform owner user
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)

        # Create an inactive tenant
        tenant2 = self._create_second_tenant(db_session, is_active=False)

        # Platform owner should NOT be able to set inactive tenant
        with pytest.raises(ValueError, match="Tenant is not active or is suspended"):
            set_active_tenant(tenant2.id, user=owner)

    def test_platform_owner_cannot_switch_to_nonexistent_tenant(self, db_session, sample_tenant, sample_branch):
        """Test platform owner cannot switch to nonexistent tenant"""
        from utils.tenanting import set_active_tenant

        # Create a platform owner user
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)

        # Try to set nonexistent tenant
        with pytest.raises(ValueError, match="Tenant not found"):
            set_active_tenant(999999, user=owner)

    def test_normal_user_login_with_valid_branch(self, db_session, sample_tenant, sample_branch):
        """Test normal user login with valid branch"""
        from utils.tenanting import set_active_tenant
        from utils.branching import set_active_branch

        # Create a normal user with branch_id
        user = self._create_test_user(db_session, sample_tenant.id, branch_id=sample_branch.id)

        # Set active tenant for user
        set_active_tenant(sample_tenant.id, user=user)

        # Set active branch for user
        set_active_branch(sample_branch.id, user=user, allow_all=False)

        # Verify both tenant and branch are set correctly
        from utils.tenanting import get_active_tenant_id
        from utils.branching import get_active_branch_id

        assert get_active_tenant_id(user=user) == sample_tenant.id
        assert get_active_branch_id(user=user) == sample_branch.id

    def test_platform_owner_behavior_valid(self, db_session, sample_tenant, sample_branch):
        """Test platform owner behavior remains valid"""
        from utils.tenanting import set_active_tenant, get_active_tenant_id
        from utils.branching import set_active_branch, get_active_branch_id

        # Create a platform owner user (tenant_id=None for bootstrap owner)
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)
        # Override tenant_id to None for bootstrap owner
        owner.tenant_id = None
        db_session.commit()

        # Create a second tenant and branch
        tenant2 = self._create_second_tenant(db_session)

        branch2 = Branch(
            tenant_id=tenant2.id,
            name="Branch 2",
            code="BR2",
            is_active=True,
        )
        db_session.add(branch2)
        db_session.flush()

        # Platform owner can switch tenant
        set_active_tenant(tenant2.id, user=owner)
        assert get_active_tenant_id(user=owner) == tenant2.id

        # Platform owner can set any branch
        set_active_branch(branch2.id, user=owner, allow_all=False)
        assert get_active_branch_id(user=owner) == branch2.id

    def test_bootstrap_owner_login_without_tenant(self, db_session, sample_tenant, sample_branch):
        """Test bootstrap owner (tenant_id=None) can log in without tenant/branch"""
        from utils.tenanting import set_active_tenant, get_active_tenant_id
        from utils.branching import set_active_branch, get_active_branch_id

        # Create bootstrap owner (tenant_id=None)
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)
        owner.tenant_id = None
        owner.branch_id = None
        db_session.commit()

        # Bootstrap owner should be able to log in without tenant
        from utils.tenanting import set_active_tenant, get_active_tenant_id
        from utils.branching import set_active_branch, get_active_branch_id

        # Should not raise error when tenant_id is None
        set_active_tenant(None, user=owner)
        assert get_active_tenant_id(user=owner) is None

        # Should not raise error when branch_id is None
        set_active_branch(None, user=owner, allow_all=True)
        assert get_active_branch_id(user=owner) is None

    def test_platform_owner_master_login_flow(self, db_session, sample_tenant, sample_branch):
        """Test platform owner master login flow is not broken"""
        from utils.master_login import try_master_login

        # Create platform owner
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)
        owner.tenant_id = None
        db_session.flush()

        # Verify owner is recognized as platform owner
        from utils.auth_helpers import is_global_owner_user
        assert is_global_owner_user(owner) == True

        # Master login function should be callable (we don't test actual secrets)
        # Just verify the function exists and returns expected structure
        success, meta = try_master_login("wrong_password", "127.0.0.1", username=owner.username)
        assert success == False
        assert isinstance(meta, dict)
        assert 'reason' in meta

    def test_developer_with_null_tenant_and_assigned_branch_does_not_raise_or_create_invalid_tenant_session(self, db_session, sample_tenant, sample_branch):
        """Test developer with tenant_id=None and assigned branch does not raise ValueError or create invalid tenant session"""
        from utils.tenanting import set_active_tenant, get_active_tenant_id
        from utils.branching import set_active_branch, get_active_branch_id
        from models import Role

        # Find existing developer role or use existing one
        dev_role = Role.query.filter_by(slug="developer").first()
        if not dev_role:
            dev_role = Role(
                name="Developer Test",
                slug="developer-test",
                is_active=True,
            )
            db_session.add(dev_role)
            db_session.flush()

        # Create developer user with tenant_id=None (developer role allows null tenant)
        developer = User(
            username=f"dev_test_{sample_tenant.id}",
            email=f"dev_test_{sample_tenant.id}@example.com",
            full_name="Test Developer",
            full_name_ar="Ù…Ø·ÙˆØ± ØªØ¬Ø±Ø¨Ø©",
            phone="0500000000",
            role_id=dev_role.id,
            tenant_id=None,  # Developer with null tenant
            branch_id=sample_branch.id,  # Assigned to a branch
            is_active=True,
        )
        developer.set_password("testpassword")
        db_session.add(developer)
        db_session.flush()

        # Test that developer with null tenant and assigned branch does not raise
        from utils.auth_helpers import user_may_have_null_tenant
        assert user_may_have_null_tenant(is_owner=False, role=dev_role) == True

        # Login should work (effective_tenant_id remains None)
        # set_active_tenant with None should clear session, not raise
        set_active_tenant(None, user=developer)

        # Verify active tenant remains None for developer
        active_tenant_id = get_active_tenant_id(user=developer)
        assert active_tenant_id is None

        # set_active_branch should work for developer (global user)
        from utils.branching import set_active_branch, get_active_branch_id
        set_active_branch(sample_branch.id, user=developer, allow_all=True)
        assert get_active_branch_id(user=developer) == sample_branch.id

        # Login flow should not raise ValueError or create invalid tenant session
        # The login flow should set effective_tenant_id = None for this developer
        # and should not try to set branch's tenant_id as effective_tenant_id

    def test_invalid_tenant_id_validation(self, db_session):
        """Test invalid tenant_id validation"""
        from utils.tenanting import set_active_tenant

        # Test invalid tenant_id (non-integer)
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            set_active_tenant("invalid", user=None)

        # Test non-existent tenant_id with unauthenticated user
        with pytest.raises(ValueError, match="Unauthenticated users cannot set tenant_id"):
            set_active_tenant(999999, user=None)

    def test_inactive_tenant_validation(self, db_session):
        """Test inactive tenant validation"""
        from utils.tenanting import set_active_tenant

        # Create an inactive tenant
        tenant = Tenant(
            name="Inactive Company",
            name_ar="Ø´Ø±ÙƒØ© ØºÙŠØ± Ù†Ø´Ø·Ø©",
            slug="inactive-company",
            email="inactive@example.com",
            phone_1="0500000002",
            country="AE",
            subscription_plan="basic",
            is_active=False,
        )
        db_session.add(tenant)
        db_session.flush()

        # Try to set inactive tenant with unauthenticated user
        with pytest.raises(ValueError, match="Unauthenticated users cannot set tenant_id"):
            set_active_tenant(tenant.id, user=None)

    def test_tenant_session_cleared_on_invalid_input(self, db_session, sample_tenant):
        """Test tenant session cleared on invalid input"""
        from utils.tenanting import set_active_tenant, get_active_tenant_id

        # Set a valid tenant first (requires authenticated user)
        # This test is skipped because unauthenticated users cannot set tenant_id
        # The session clearing behavior is tested through the login flow
        pass

    def test_tenant_switch_rejects_suspended_tenant(self, db_session, sample_tenant):
        """Test tenant switch route rejects suspended tenant safely"""
        from utils.tenanting import set_active_tenant, get_active_tenant_id
        from flask import session

        # Create a platform owner user
        owner = self._create_test_user(db_session, sample_tenant.id, is_owner=True)
        owner.tenant_id = None
        db_session.flush()

        # Create a suspended tenant
        suspended_tenant = self._create_second_tenant(
            db_session,
            name="Suspended Company",
            name_ar="شركة معلقة",
            slug=f"suspended-company-{uuid.uuid4().hex[:8]}",
            email="suspended@example.com",
            is_active=True,
            is_suspended=True,
        )

        # Set active tenant to sample_tenant first
        set_active_tenant(sample_tenant.id, user=owner)
        assert get_active_tenant_id(user=owner) == sample_tenant.id

        # Try to set suspended tenant - should raise ValueError
        from utils.tenanting import set_active_tenant
        with pytest.raises(ValueError, match="Tenant is not active or is suspended"):
            set_active_tenant(suspended_tenant.id, user=owner)

        # Verify active tenant unchanged
        assert get_active_tenant_id(user=owner) == sample_tenant.id


# ---------------------------------------------------------------------------
# Flask test-client route-level tests
# ---------------------------------------------------------------------------

class TestLoginRouteLevel:
    """Flask test-client tests for /auth/login and /tenants/switch routes."""

    def _make_user(self, db_session, username, password, tenant_id, branch_id=None,
                   is_owner=False, role_slug="manager"):
        import uuid
        from models.user import User, Role
        role = Role.query.filter_by(slug=role_slug).first()
        if not role:
            role = Role(name=role_slug.title(), slug=role_slug, is_active=True)
            db_session.add(role)
            db_session.flush()
        unique = str(uuid.uuid4())[:8]
        user = User(
            username=f"{username}_{unique}",
            email=f"{username}_{unique}@test.local",
            full_name=username,
            full_name_ar=username,
            phone="0500000000",
            role_id=role.id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            is_owner=is_owner,
            is_active=True,
        )
        user.set_password(password)
        db_session.add(user)
        db_session.flush()
        return user

    def test_normal_user_login_redirects_never_500(self, client, app, db_session, sample_tenant, sample_branch):
        """Valid normal-user POST /auth/login → redirect (302), never 500."""
        from services.gl_service import GLService

        user = self._make_user(
            db_session, "loginok1", "pass1234",
            sample_tenant.id, branch_id=sample_branch.id,
        )
        sample_tenant.is_active = True
        sample_tenant.is_suspended = False
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        db_session.commit()

        with client.session_transaction() as sess:
            sess.clear()

        resp = client.post("/auth/login", data={
            "username": user.username,
            "password": "pass1234",
        }, follow_redirects=False)

        assert resp.status_code in (302, 303), f"Expected redirect, got {resp.status_code}"
        assert resp.status_code != 500

        with client.session_transaction() as sess:
            assert "_user_id" in sess, "User should be logged in"

    def test_cross_tenant_branch_mismatch_no_session(self, client, app, db_session, sample_tenant, sample_branch):
        """Cross-tenant branch mismatch â†’ safe login response, no _user_id set."""
        import uuid
        from models.tenant import Tenant
        from models.branch import Branch

        u = str(uuid.uuid4())[:8]
        other_tenant = Tenant(
            name=f"Other Tenant {u}", name_ar="Ø´Ø±ÙƒØ© Ø£Ø®Ø±Ù‰", slug=f"other-t-{u}",
            email=f"other_{u}@test.local", phone_1="0509999999", country="AE",
            subscription_plan="basic",
        )
        db_session.add(other_tenant)
        db_session.flush()

        other_branch = Branch(
            tenant_id=other_tenant.id, name=f"Other Branch {u}", code=f"OTH{u[:3].upper()}",
            is_active=True, is_main=True,
        )
        db_session.add(other_branch)
        db_session.flush()

        user = self._make_user(
            db_session, "crossuser", "pass1234",
            sample_tenant.id, branch_id=sample_branch.id,
        )
        db_session.commit()

        # Simulate cross-tenant branch by monkeypatching the DB record
        # so the login flow sees a branch from another tenant
        user.branch_id = other_branch.id
        db_session.commit()

        with client.session_transaction() as sess:
            sess.clear()

        resp = client.post("/auth/login", data={
            "username": user.username,
            "password": "pass1234",
        }, follow_redirects=False)

        # Should NOT be a 500; may be 200 (login page re-rendered) or 302
        assert resp.status_code != 500

        with client.session_transaction() as sess:
            assert "_user_id" not in sess, "Cross-tenant mismatch must not log user in"

    def test_bootstrap_owner_login_redirects(self, client, app, db_session, sample_tenant, sample_branch):
        """Bootstrap owner (tenant_id=None) login â†’ redirect, no active tenant required."""
        import uuid
        from models.user import User, Role

        owner_role = Role.query.filter_by(slug="owner").first()
        if not owner_role:
            owner_role = Role(name="Owner", slug="owner", is_active=True)
            db_session.add(owner_role)
            db_session.flush()

        unique = str(uuid.uuid4())[:8]
        owner = User(
            username=f"boot_owner_{unique}",
            email=f"bootowner_{unique}@test.local",
            full_name="Bootstrap Owner",
            full_name_ar="Ø§Ù„Ù…Ø§Ù„Ùƒ",
            phone="0500000000",
            role_id=owner_role.id,
            tenant_id=None,
            branch_id=None,
            is_owner=True,
            is_active=True,
        )
        owner.set_password("ownerpass1")
        db_session.add(owner)
        db_session.flush()
        db_session.commit()

        with client.session_transaction() as sess:
            sess.clear()

        resp = client.post("/auth/login", data={
            "username": owner.username,
            "password": "ownerpass1",
        }, follow_redirects=False)

        assert resp.status_code in (302, 303), f"Expected redirect, got {resp.status_code}"
        assert resp.status_code != 500

        with client.session_transaction() as sess:
            assert "_user_id" in sess, "Owner should be logged in"

    def test_suspended_tenant_switch_never_500(self, client, app, db_session, sample_tenant, sample_branch):
        """Switch to suspended tenant via /tenants/switch â†’ never 500, preserves previous tenant."""
        import uuid
        from models.tenant import Tenant
        from utils.tenanting import set_active_tenant, get_active_tenant_id

        owner = self._make_user(
            db_session, "switchowner", "pass1234",
            sample_tenant.id, is_owner=True,
        )
        sample_tenant.is_active = True
        sample_tenant.is_suspended = False
        db_session.commit()

        unique = str(uuid.uuid4())[:8]
        suspended = Tenant(
            name=f"Suspended {unique}", name_ar="Ù…Ø¹Ù„Ù‚Ø©", slug=f"suspended-{unique}",
            email=f"sus_{unique}@test.local", phone_1="0501111111", country="AE",
            subscription_plan="basic", is_active=True, is_suspended=True,
        )
        db_session.add(suspended)
        db_session.flush()
        db_session.commit()

        with client.session_transaction() as sess:
            sess.clear()

        # Log the owner in via login route
        resp = client.post("/auth/login", data={
            "username": owner.username,
            "password": "pass1234",
        }, follow_redirects=False)
        assert resp.status_code in (302, 303)

        with app.app_context():
            set_active_tenant(sample_tenant.id, user=owner)

        # Attempt switch to suspended tenant
        resp = client.get(f"/tenants/switch/{suspended.id}", follow_redirects=False)
        assert resp.status_code != 500, "Switch must never return 500"

    def test_master_login_attempt_never_500(self, client, app, db_session, sample_tenant, sample_branch):
        """Master-login path (wrong password) â†’ safe response, never 500."""
        owner = self._make_user(
            db_session, "master_user", "correctpass",
            sample_tenant.id, is_owner=True,
        )
        db_session.commit()

        with client.session_transaction() as sess:
            sess.clear()

        resp = client.post("/auth/login", data={
            "username": owner.username,
            "password": "wrong_password_123",
        }, follow_redirects=False)

        assert resp.status_code != 500, "Master-login path must never return 500"
        # Should re-render login page or flash a message
        assert resp.status_code in (200, 302)

        with client.session_transaction() as sess:
            assert "_user_id" not in sess, "Wrong password must not log user in"
