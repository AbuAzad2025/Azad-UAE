"""Gap100 for models/tenant.py — explicit-user None paths (line 198 + arcs).

Existing tests call ``get_current()`` without a user (warning path) or with an
active relationship (early return). These tests pass an explicit authenticated
non-owner user whose relationship is inactive or missing, hitting the
``return None`` fallback and both arcs of the relationship guard.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestGetCurrentExplicitNone:
    def test_inactive_relationship_returns_none(self, app, mocker):
        from models.tenant import Tenant

        rel = MagicMock(is_active=False)
        user = MagicMock(is_authenticated=True, tenant=rel)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/"):
            assert Tenant.get_current(user=user) is None

    def test_missing_relationship_returns_none(self, app, mocker):
        from models.tenant import Tenant

        user = MagicMock(is_authenticated=True, tenant=None)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/"):
            assert Tenant.get_current(user=user) is None
