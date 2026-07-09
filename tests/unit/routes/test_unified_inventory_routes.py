from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import app_factory, bypass_permission_auth, unauthenticated_client


def _uinv_patches(tid=1, campaigns=None, claims=None, shipments=None):
    campaigns = campaigns or []
    claims = claims or []
    shipments = shipments or []
    stack = ExitStack()
    stack.enter_context(patch('routes.unified_inventory.get_active_tenant_id', return_value=tid))
    stack.enter_context(patch('routes.unified_inventory.render_template', return_value='ok'))
    stack.enter_context(patch('routes.unified_inventory.LoggingCore.log_audit'))
    camp_q = MagicMock()
    camp_q.filter_by.return_value.order_by.return_value.all.return_value = campaigns
    claim_q = MagicMock()
    claim_q.filter_by.return_value.order_by.return_value.all.return_value = claims
    ship_q = MagicMock()
    ship_q.filter_by.return_value.order_by.return_value.all.return_value = shipments
    stack.enter_context(patch('routes.unified_inventory.Campaign', camp_q))
    stack.enter_context(patch('routes.unified_inventory.WarrantyClaim', claim_q))
    stack.enter_context(patch('routes.unified_inventory.Shipment', ship_q))
    mock_db = stack.enter_context(patch('routes.unified_inventory.db'))
    return stack, mock_db


@contextmanager
def uinv_ctx(**kwargs):
    stack, mock_db = _uinv_patches(**kwargs)
    with stack:
        yield mock_db


@pytest.fixture
def uinv_client(app_factory, bypass_permission_auth):
    from routes.unified_inventory import uinv_bp
    return app_factory(uinv_bp).test_client()


class TestCampaignsRoutes:
    def test_campaigns_index_with_tenant(self, uinv_client):
        with uinv_ctx(tid=1, campaigns=[MagicMock(id=1)]):
            resp = uinv_client.get('/uinv/campaigns')
        assert resp.status_code == 200

    def test_campaigns_index_without_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            resp = uinv_client.get('/uinv/campaigns')
        assert resp.status_code == 200

    def test_campaigns_create_success(self, uinv_client):
        with uinv_ctx(tid=1):
            resp = uinv_client.post('/uinv/campaigns', data={
                'name': 'Summer', 'campaign_type': 'percentage',
                'coupon_code': 'SUM', 'discount_value': '10', 'min_order_amount': '50',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_campaigns_create_no_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            resp = uinv_client.post('/uinv/campaigns', data={'name': 'X'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_campaigns_create_rollback_on_error(self, uinv_client):
        with uinv_ctx(tid=1) as mock_db:
            mock_db.session.commit.side_effect = RuntimeError('db')
            resp = uinv_client.post('/uinv/campaigns', data={'name': 'Bad'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_unauthenticated_campaigns(self, uinv_client):
        with unauthenticated_client(uinv_client):
            resp = uinv_client.get('/uinv/campaigns')
        assert resp.status_code == 401


class TestWarrantyRoutes:
    def test_warranty_index(self, uinv_client):
        with uinv_ctx(claims=[MagicMock()]):
            assert uinv_client.get('/uinv/warranty').status_code == 200

    def test_warranty_index_no_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            assert uinv_client.get('/uinv/warranty').status_code == 200

    def test_warranty_create_success(self, uinv_client):
        with uinv_ctx(tid=1):
            resp = uinv_client.post('/uinv/warranty', data={
                'sale_id': '1', 'sale_line_id': '2', 'product_id': '3',
                'claim_type': 'repair', 'description': 'broken',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_warranty_create_no_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            resp = uinv_client.post('/uinv/warranty', data={'sale_id': '1', 'product_id': '1'})
        assert resp.status_code == 302

    def test_warranty_create_error_rolls_back(self, uinv_client):
        with uinv_ctx(tid=1) as mock_db:
            mock_db.session.commit.side_effect = ValueError('bad')
            resp = uinv_client.post('/uinv/warranty', data={'sale_id': 'x', 'product_id': '1'})
        assert resp.status_code == 302


class TestShipmentRoutes:
    def test_shipments_index(self, uinv_client):
        with uinv_ctx(shipments=[MagicMock()]):
            assert uinv_client.get('/uinv/shipments').status_code == 200

    def test_shipments_index_no_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            assert uinv_client.get('/uinv/shipments').status_code == 200

    def test_shipments_create_success(self, uinv_client):
        with uinv_ctx(tid=1):
            resp = uinv_client.post('/uinv/shipments', data={
                'carrier_name': 'DHL', 'tracking_number': 'TRK1',
                'source_id': '10', 'shipping_cost': '25', 'customs_duty': '5', 'insurance': '2',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_shipments_create_no_tenant(self, uinv_client):
        with uinv_ctx(tid=None):
            resp = uinv_client.post('/uinv/shipments', data={'source_id': '1'})
        assert resp.status_code == 302

    def test_shipments_create_error_rolls_back(self, uinv_client):
        with uinv_ctx(tid=1) as mock_db:
            mock_db.session.commit.side_effect = RuntimeError('fail')
            resp = uinv_client.post('/uinv/shipments', data={'source_id': '1'})
        assert resp.status_code == 302
