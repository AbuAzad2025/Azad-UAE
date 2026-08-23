"""Unit tests for UserService owner-panel lookup helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import NotFound

from extensions import db
from models import Branch, Sale, Tenant
from services.user_service import UserService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _role_cls(rows):
    cls = MagicMock()
    cls.query.filter_by.return_value.all.return_value = rows
    return cls


def _other_tenant():
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Company {unique}",
        name_ar="شركة أخرى",
        slug=f"other-company-{unique}",
        email=f"other-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
        is_active=True,
    )
    db.session.add(tenant)
    db.session.flush()
    return tenant


class TestRoleLookups:
    def test_get_role_returns_role(self, db_session, sample_role):
        assert UserService.get_role(sample_role.id).id == sample_role.id

    def test_get_role_none_without_id(self):
        assert UserService.get_role(None) is None

    def test_creatable_roles_exclude_owner_and_developer(self, mocker):
        seller = MagicMock(slug="seller", is_active=True)
        owner = MagicMock(slug="owner", is_active=True)
        developer = MagicMock(slug="developer", is_active=True)
        mocker.patch("models.Role", _role_cls([owner, developer, seller]))
        mocker.patch("utils.auth_helpers.role_level_for", return_value=10)

        creatable = {r.slug for r in UserService.creatable_roles(999)}

        assert creatable == {"seller"}

    def test_roles_visible_to_level_keeps_owner_slug(self, mocker):
        owner = MagicMock(slug="owner", is_active=True)
        mocker.patch("models.Role", _role_cls([owner]))
        mocker.patch("utils.auth_helpers.role_level_for", return_value=10)

        assert [r.slug for r in UserService.roles_visible_to_level(999)] == ["owner"]

    def test_roles_visible_to_level_drops_higher_levels_and_inactive(self, mocker):
        junior = MagicMock(slug="junior", is_active=True)
        senior = MagicMock(slug="senior", is_active=True)
        inactive = MagicMock(slug="inactive-role", is_active=False)

        def level_for(slug):
            return 5 if slug == "junior" else 500

        mocker.patch("models.Role", _role_cls([junior, senior, inactive]))
        mocker.patch("utils.auth_helpers.role_level_for", side_effect=level_for)

        visible = {r.slug for r in UserService.roles_visible_to_level(100)}

        assert visible == {"junior"}


class TestUserLookups:
    def test_get_user_or_404_returns_user(self, sample_user):
        assert UserService.get_user_or_404(sample_user.id).id == sample_user.id

    def test_get_user_or_404_raises_when_missing(self):
        with pytest.raises(NotFound):
            UserService.get_user_or_404(987654321)

    def test_find_username_conflict_in_tenant(self, sample_user):
        conflict = UserService.find_username_conflict_in_tenant(sample_user.username, sample_user.tenant_id)
        assert conflict is not None
        assert conflict.id == sample_user.id

    def test_find_username_conflict_scoped_to_other_tenant(self, db_session, sample_user):
        other = _other_tenant()
        assert UserService.find_username_conflict_in_tenant(sample_user.username, other.id) is None

    def test_tenant_branches_filters_by_tenant_and_orders(self, db_session, sample_tenant, sample_branch):
        other = _other_tenant()
        other_branch = Branch(
            tenant_id=other.id,
            name="Other Branch",
            code=f"OTH-{uuid.uuid4().hex[:4].upper()}",
            is_active=True,
            is_main=True,
        )
        db.session.add(other_branch)
        db.session.flush()

        scoped_ids = {b.id for b in UserService.tenant_branches(sample_tenant.id)}
        assert sample_branch.id in scoped_ids
        assert other_branch.id not in scoped_ids

        unscoped_ids = {b.id for b in UserService.tenant_branches(None)}
        assert {sample_branch.id, other_branch.id} <= unscoped_ids

    def test_active_tenants_excludes_inactive(self, db_session, sample_tenant):
        inactive = Tenant(
            name="Inactive Company",
            name_ar="شركة موقوفة",
            slug=f"inactive-company-{uuid.uuid4().hex[:8]}",
            email=f"inactive-{uuid.uuid4().hex[:8]}@example.com",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
            is_active=False,
        )
        db.session.add(inactive)
        db.session.flush()

        tenants = {t.id for t in UserService.active_tenants()}

        assert sample_tenant.id in tenants
        assert inactive.id not in tenants


class TestUserProfileContext:
    def _sale(self, tenant_id, seller_id, customer_id):
        sale = Sale(
            tenant_id=tenant_id,
            customer_id=customer_id,
            sale_number=f"SVC-{uuid.uuid4().hex[:8]}",
            sale_date=datetime.now(UTC),
            subtotal=100,
            total_amount=100,
            amount=100,
            amount_aed=100,
            currency="AED",
            payment_status="unpaid",
            status="confirmed",
            source="internal",
            seller_id=seller_id,
        )
        db.session.add(sale)
        db.session.flush()
        return sale

    def test_context_counts_scoped_rows(self, db_session, sample_tenant, sample_user, sample_customer):
        self._sale(sample_tenant.id, sample_user.id, sample_customer.id)
        self._sale(sample_tenant.id, sample_user.id, sample_customer.id)

        context = UserService.user_profile_context(sample_user.id, sample_tenant.id)

        assert context["stats"]["sales_count"] == 2
        assert context["stats"]["sales_total"] == 200
        assert len(context["recent_sales"]) == 2
        assert all(s.seller_id == sample_user.id for s in context["recent_sales"])

    def test_context_unscoped_when_no_tenant(self, db_session, sample_tenant, sample_user, sample_customer):
        self._sale(sample_tenant.id, sample_user.id, sample_customer.id)

        context = UserService.user_profile_context(sample_user.id, None)

        assert context["stats"]["sales_count"] >= 1
