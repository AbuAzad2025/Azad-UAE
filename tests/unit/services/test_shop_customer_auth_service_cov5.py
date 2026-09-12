"""Cov5: shop_customer_auth_service — default session + flush-failure arcs."""

from __future__ import annotations

import pytest


def test_get_logged_in_account_default_session_empty(app, sample_tenant):
    from services.shop_customer_auth_service import ShopCustomerAuthService

    with app.test_request_context("/"):
        assert ShopCustomerAuthService.get_logged_in_account(sample_tenant.id) is None


def test_register_flush_failure(db_session, sample_tenant, mocker):
    from extensions import db
    from services.shop_customer_auth_service import ShopCustomerAuthService

    mocker.patch.object(db.session, "flush", side_effect=[None, RuntimeError("db down")])
    with pytest.raises(RuntimeError, match="db down"):
        ShopCustomerAuthService.register(
            sample_tenant.id, "Cov5", "cov5reg@example.com", "0501112222", "password123"
        )
