"""Route tests for the POS register's quick-customer and stock-summary APIs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import unauthenticated_client
from tests.unit.routes.test_pos_v2_routes import _pos_enabled_patches


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    return app_factory(pos_bp).test_client()


def test_quick_customer_create(pos_client):
    customer = MagicMock(
        id=42,
        phone="",
        customer_type="individual",
        email=None,
        name_ar="",
        preferred_currency="AED",
    )
    customer.name = "New Customer"
    with _pos_enabled_patches():
        with (
            patch("routes.pos.atomic_transaction"),
            patch("utils.tenant_limits.check_customers_limit"),
            patch("utils.currency_utils.resolve_default_currency", return_value="AED"),
            patch("services.logging_core.LoggingCore.log_audit"),
            patch("services.customer_service.CustomerService.create_customer", return_value=customer),
        ):
            resp = pos_client.post("/pos/api/customers/create", json={"name": "New Customer"})
    assert resp.status_code == 201
    assert resp.get_json()["data"]["name"] == "New Customer"


def test_quick_customer_requires_name(pos_client):
    with _pos_enabled_patches():
        resp = pos_client.post("/pos/api/customers/create", json={})
    assert resp.status_code == 400


def test_stock_summary(pos_client):
    with _pos_enabled_patches():
        with (
            patch("services.stock_service.StockService.get_low_stock_products", return_value=[1, 2]),
            patch("services.stock_service.StockService.get_out_of_stock_products", return_value=[3]),
            patch("routes.pos.tenant_query", return_value=MagicMock(count=MagicMock(return_value=10))),
        ):
            resp = pos_client.get("/pos/api/stock/summary")
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"available": 7, "low": 2, "out": 1, "total": 10}


def test_new_apis_require_login(pos_client):
    with _pos_enabled_patches(), unauthenticated_client(pos_client):
        assert pos_client.get("/pos/api/stock/summary").status_code == 401
