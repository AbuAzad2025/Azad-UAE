"""Unit tests for utils/tenant_security.py — route-level tenant guard decorators.

Covers the real guard outcomes (400/403/404 aborts and pass-through) using
real DB rows and request contexts. Cross-tenant access must always surface
as 404 (no existence leak); missing tenant context as 403 (context guard)
or 404 (ownership guard).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import g
from werkzeug.exceptions import BadRequest, Forbidden, NotFound


@pytest.fixture
def request_ctx(app):
    with app.test_request_context("/"):
        yield


def _user(is_owner=False):
    return MagicMock(is_authenticated=True, is_owner=is_owner)


class TestRequireTenantContext:
    def test_passes_with_active_tenant(self, request_ctx, sample_tenant):
        from utils.tenant_security import require_tenant_context

        g.active_tenant_id = sample_tenant.id

        @require_tenant_context
        def view():
            return "ok"

        assert view() == "ok"

    def test_aborts_403_without_tenant_for_company_user(self, request_ctx):
        from utils.tenant_security import require_tenant_context

        @require_tenant_context
        def view():
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            with pytest.raises(Forbidden):
                view()

    def test_passes_without_tenant_for_platform_owner(self, request_ctx):
        from utils.tenant_security import require_tenant_context

        @require_tenant_context
        def view():
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=True)):
            assert view() == "ok"


class TestValidateTenantOwnership:
    def test_passes_when_resource_matches_tenant(
        self, request_ctx, sample_tenant, sample_product
    ):
        from models import Product
        from utils.tenant_security import validate_tenant_ownership

        g.active_tenant_id = sample_tenant.id

        @validate_tenant_ownership(Product)
        def view(product_id):
            return f"ok:{product_id}"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            assert view(product_id=sample_product.id) == f"ok:{sample_product.id}"

    def test_aborts_404_for_cross_tenant_resource(
        self, request_ctx, db_session, sample_product
    ):
        from models import Product, Tenant
        from utils.tenant_security import validate_tenant_ownership

        other = Tenant(
            name="Other Co TS",
            name_ar="أخرى",
            slug="other-co-ts",
            email="other-ts@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()
        g.active_tenant_id = other.id

        @validate_tenant_ownership(Product)
        def view(product_id):
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            with pytest.raises(NotFound):
                view(product_id=sample_product.id)

    def test_aborts_404_for_missing_resource(self, request_ctx, sample_tenant):
        from models import Product
        from utils.tenant_security import validate_tenant_ownership

        g.active_tenant_id = sample_tenant.id

        @validate_tenant_ownership(Product)
        def view(product_id):
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            with pytest.raises(NotFound) as exc_info:
                view(product_id=999999)
        assert "Product not found" in exc_info.value.description

    def test_aborts_400_when_no_id_parameter(self, request_ctx, sample_tenant):
        from models import Product
        from utils.tenant_security import validate_tenant_ownership

        g.active_tenant_id = sample_tenant.id

        @validate_tenant_ownership(Product)
        def view():
            return "ok"

        with pytest.raises(BadRequest):
            view()

    def test_aborts_404_without_tenant_context_for_company_user(
        self, request_ctx, sample_product
    ):
        from models import Product
        from utils.tenant_security import validate_tenant_ownership

        @validate_tenant_ownership(Product)
        def view(product_id):
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            with pytest.raises(NotFound):
                view(product_id=sample_product.id)

    def test_unscoped_resource_requires_owner(self, request_ctx, sample_tenant):
        # Tenant itself has no tenant_id attribute → platform-owner only.
        from models import Tenant
        from utils.tenant_security import validate_tenant_ownership

        g.active_tenant_id = sample_tenant.id

        @validate_tenant_ownership(Tenant)
        def view(id):
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            with pytest.raises(NotFound):
                view(id=sample_tenant.id)

        with patch("utils.tenant_security.current_user", _user(is_owner=True)):
            assert view(id=sample_tenant.id) == "ok"

    def test_falls_back_to_first_parameter(
        self, request_ctx, sample_tenant, sample_product
    ):
        from models import Product
        from utils.tenant_security import validate_tenant_ownership

        g.active_tenant_id = sample_tenant.id

        @validate_tenant_ownership(Product)
        def view(thing):
            return "ok"

        with patch("utils.tenant_security.current_user", _user(is_owner=False)):
            assert view(thing=sample_product.id) == "ok"
