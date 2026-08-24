"""Tests for routes/transfers.py — 8 distinct endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import unauthenticated_client


def _mock_transfer(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.tenant_id = kwargs.get("tenant_id", 1)
    t.transfer_number = kwargs.get("transfer_number", "TR-2026-001")
    t.status = kwargs.get("status", "draft")
    t.from_warehouse_id = kwargs.get("from_warehouse_id", 1)
    t.to_warehouse_id = kwargs.get("to_warehouse_id", 2)
    t.lines = kwargs.get("lines", [])
    return t


@pytest.fixture
def transfers_client(app_factory, bypass_permission_auth):
    from routes.transfers import transfers_bp

    app = app_factory(transfers_bp)
    return app.test_client()


@pytest.fixture
def transfers_mocks():
    t = _mock_transfer()
    patches = [
        patch("routes.transfers.TransferService.list_transfers", return_value=[t]),
        patch("routes.transfers.TransferService.create_transfer", return_value=t),
        patch("routes.transfers.TransferService.get_transfer", return_value=t),
        patch("routes.transfers.TransferService.approve_transfer", return_value=t),
        patch("routes.transfers.TransferService.ship_transfer", return_value=t),
        patch("routes.transfers.TransferService.confirm_receive", return_value=t),
        patch("routes.transfers.TransferService.complete_transfer", return_value=t),
        patch("routes.transfers.TransferService.cancel_transfer", return_value=t),
        patch("routes.transfers.render_template", return_value="ok"),
    ]
    for p in patches:
        p.start()
    yield {"transfer": t}
    for p in reversed(patches):
        p.stop()


class TestTransfersAuth:
    def test_index_requires_login(self, transfers_client):
        with unauthenticated_client(transfers_client):
            resp = transfers_client.get("/transfers/")
        assert resp.status_code == 401

    def test_index_forbidden(self, transfers_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = transfers_client.get("/transfers/")
        assert resp.status_code == 403

    def test_create_forbidden(self, transfers_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = transfers_client.get("/transfers/create")
        assert resp.status_code == 403

    def test_approve_forbidden(self, transfers_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = transfers_client.post("/transfers/1/approve")
        assert resp.status_code == 403


class TestTransfersIndex:
    def test_index_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.get("/transfers/")
        assert resp.status_code == 200

    def test_index_with_filters(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.list_transfers", return_value=[]) as m:
            resp = transfers_client.get("/transfers/?status=draft")
        assert resp.status_code == 200
        m.assert_called_once()


class TestTransfersCreate:
    def test_create_get_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.get("/transfers/create")
        assert resp.status_code == 200

    def test_create_post_success_redirect(self, transfers_client, transfers_mocks):
        resp = transfers_client.post(
            "/transfers/create",
            data={"from_warehouse_id": "1", "to_warehouse_id": "2", "lines-0-product_id": "1", "lines-0-quantity": "5"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/transfers/1" in resp.location

    def test_create_post_validation_error_stays_200(self, transfers_client, transfers_mocks):
        with patch(
            "routes.transfers.TransferService.create_transfer",
            side_effect=ValueError("المستودعان يجب أن يكونا مختلفين."),
        ):
            resp = transfers_client.post("/transfers/create", data={"from_warehouse_id": "1", "to_warehouse_id": "1"})
        assert resp.status_code == 200

    def test_create_post_key_error_stays_200(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.create_transfer", side_effect=KeyError("from_warehouse_id")):
            resp = transfers_client.post("/transfers/create", data={})
        assert resp.status_code == 200


class TestTransfersDetail:
    def test_detail_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.get("/transfers/1")
        assert resp.status_code == 200

    def test_detail_tenant_isolation_404(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.get_transfer", side_effect=ValueError("طلب النقل غير موجود.")):
            with pytest.raises(ValueError, match="طلب النقل غير موجود"):
                transfers_client.get("/transfers/999")


class TestTransfersApprove:
    def test_approve_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.post("/transfers/1/approve", follow_redirects=False)
        assert resp.status_code == 302

    def test_approve_validation_error_redirect(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.approve_transfer", side_effect=ValueError("فقط المسودات")):
            resp = transfers_client.post("/transfers/1/approve", follow_redirects=False)
        assert resp.status_code == 302


class TestTransfersShip:
    def test_ship_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.post("/transfers/1/ship", follow_redirects=False)
        assert resp.status_code == 302

    def test_ship_validation_error(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.ship_transfer", side_effect=ValueError("يجب الموافقة أولاً")):
            resp = transfers_client.post("/transfers/1/ship", follow_redirects=False)
        assert resp.status_code == 302


class TestTransfersReceive:
    def test_receive_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.post("/transfers/1/receive", follow_redirects=False)
        assert resp.status_code == 302
        assert "/transfers/1" in resp.location

    def test_receive_validation_error(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.confirm_receive", side_effect=ValueError("يجب أن يكون قيد النقل")):
            resp = transfers_client.post("/transfers/1/receive", follow_redirects=False)
        assert resp.status_code == 302

    def test_receive_complete_called(self, transfers_client, transfers_mocks):
        # confirm_receive + complete_transfer both called on happy path
        with patch(
            "routes.transfers.TransferService.complete_transfer", return_value=_mock_transfer(status="completed")
        ) as mock_complete:
            resp = transfers_client.post("/transfers/1/receive", follow_redirects=False)
        assert resp.status_code == 302
        mock_complete.assert_called_once()


class TestTransfersCancel:
    def test_cancel_happy(self, transfers_client, transfers_mocks):
        resp = transfers_client.post("/transfers/1/cancel", follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_validation_error(self, transfers_client, transfers_mocks):
        with patch(
            "routes.transfers.TransferService.cancel_transfer", side_effect=ValueError("المكتمل لا يمكن إلغاؤه")
        ):
            resp = transfers_client.post("/transfers/1/cancel", follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_404(self, transfers_client, transfers_mocks):
        with patch("routes.transfers.TransferService.get_transfer", side_effect=ValueError("غير موجود")):
            with pytest.raises(ValueError, match="غير موجود"):
                transfers_client.post("/transfers/999/cancel", follow_redirects=False)
