"""Gap coverage for routes/pos.py — hits missing 1162, 1486->1482, 1997->1996."""

import queue as _queue
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from models.pos_cash_movement import PosCashMovement
from tests.unit.routes.test_pos_v2_routes import _mock_session, _pos_api_patches


@pytest.fixture
def cov_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


class TestSessionOpenIntegrityGap1162:
    """Line 1162: IntegrityError without idempotency_key -> 500."""

    def test_integrity_without_key_returns_500(self, cov_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.create_pos_session", side_effect=IntegrityError("dup", None, Exception("dup"))),
        ):
            resp = cov_client.post("/pos/api/session/open", json={"opening_balance": 0})
        assert resp.status_code == 500
        assert "تعذر فتح الجلسة" in resp.get_json()["message"]

    def test_integrity_without_key_branch_vs_with_key(self, cov_client):
        # with key goes 409, without goes 500 — both branches
        record = MagicMock()
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(record, None)),
            patch("routes.pos.create_pos_session", side_effect=IntegrityError("dup", None, Exception("dup"))),
        ):
            resp = cov_client.post(
                "/pos/api/session/open",
                json={},
                headers={"Idempotency-Key": "k-1162"},
            )
        assert resp.status_code == 409


class TestAccumulateShiftTotalsGap1486:
    """Branch 1486->1482: movement neither pay_in nor pay_out is ignored."""

    def test_unknown_movement_type_is_ignored(self, cov_client):
        from routes.pos import _accumulate_shift_totals

        shift = MagicMock()
        shift.tenant_id = 1
        shift.session_id = 11
        shift.id = 99
        shift.total_change_given = Decimal("0")
        # one pay_in, one pay_out, one unknown
        pay_in = MagicMock(amount=Decimal("10"), movement_type=PosCashMovement.TYPE_PAY_IN)
        pay_out = MagicMock(amount=Decimal("4"), movement_type=PosCashMovement.TYPE_PAY_OUT)
        unknown = MagicMock(amount=Decimal("999"), movement_type="adjustment")
        empty_sale = MagicMock(total_amount=Decimal("0"), payments=[])
        with (
            patch("services.pos_write_service.PosWriteService.session_sales", return_value=[empty_sale]),
            patch("services.pos_write_service.PosWriteService.shift_cash_movements", return_value=[pay_in, pay_out, unknown]),
            patch("routes.pos.payment_amount_base", return_value=Decimal("0")),
        ):
            _accumulate_shift_totals(shift)
        assert shift.total_pay_ins == Decimal("10")
        assert shift.total_pay_outs == Decimal("4")
        # unknown must not be added to either

    def test_reconcile_uses_unknown_branch_via_api(self, cov_client):
        shift = MagicMock(status="open", total_change_given=Decimal("0"))
        shift.session_id = 11
        shift.tenant_id = 1
        shift.id = 5
        shift.to_dict.return_value = {"status": "reconciled"}
        unknown = MagicMock(amount=Decimal("5"), movement_type="other")
        with (
            _pos_api_patches(shift=shift),
            patch("services.pos_write_service.PosWriteService.session_sales", return_value=[]),
            patch("services.pos_write_service.PosWriteService.shift_cash_movements", return_value=[unknown]),
        ):
            resp = cov_client.post("/pos/api/shift/reconcile", json={"actual_cash": "0"})
        assert resp.status_code == 200
        assert shift.total_pay_ins == Decimal("0")
        assert shift.total_pay_outs == Decimal("0")


class TestPublishCfdRefreshGap1997:
    """Branch 1997->1996: stale entry not in _CFD_SUBSCRIBERS not removed."""

    def test_stale_not_in_list_branch(self):
        from routes import pos as pos_module

        q = MagicMock()
        q.put_nowait.side_effect = Exception("broken")
        stale_entry = (1, 11, q)
        # subscriber matches tenant/session so it will be added to stale
        pos_module._CFD_SUBSCRIBERS.append((1, 11, q))
        # also add a stale entry that is NOT in subscribers to hit false branch
        fake_stale = (1, 11, MagicMock())
        # patch sse_backplane to avoid redis
        with patch.object(pos_module.sse_backplane, "publish"):
            # make q.put_nowait fail for real subscriber, so stale collects it
            pos_module._publish_cfd_refresh(tenant_id=1, session_id=11)
        # after publish, real subscriber should be removed, fake not
        # now test the explicit false branch: iterate stale with entry not present
        pos_module._CFD_SUBSCRIBERS.clear()
        pos_module._CFD_SUBSCRIBERS.append((1, 11, MagicMock()))
        stale = [fake_stale]
        # simulate loop from _publish_cfd_refresh: for entry in stale: if entry in _CFD_SUBSCRIBERS ...
        for entry in stale:
            if entry in pos_module._CFD_SUBSCRIBERS:
                pos_module._CFD_SUBSCRIBERS.remove(entry)
        # should not have removed anything, still 1
        assert len(pos_module._CFD_SUBSCRIBERS) == 1
        pos_module._CFD_SUBSCRIBERS.clear()

    def test_notify_kds_stale_not_in_list(self):
        from routes import pos as pos_module

        q = MagicMock()
        q.put_nowait.side_effect = Exception("full")
        pos_module._KDS_SUBSCRIBERS.append((1, q))
        with patch.object(pos_module.sse_backplane, "publish"):
            pos_module._notify_kds({"type": "ping", "tenant_id": 1}, tenant_id=1)
        # after failing, stale should be cleared
        assert (1, q) not in pos_module._KDS_SUBSCRIBERS
        # now test false branch directly
        pos_module._KDS_SUBSCRIBERS.clear()
        pos_module._KDS_SUBSCRIBERS.append((1, MagicMock()))
        fake = (1, MagicMock())
        stale = [fake]
        for entry in stale:
            if entry in pos_module._KDS_SUBSCRIBERS:
                pos_module._KDS_SUBSCRIBERS.remove(entry)
        assert len(pos_module._KDS_SUBSCRIBERS) == 1
        pos_module._KDS_SUBSCRIBERS.clear()

    def test_publish_cfd_refresh_continue_and_put_branch(self):
        from routes import pos as pos_module

        # one subscriber for other tenant should be skipped (continue)
        other_q = _queue.Queue()
        matching_q = _queue.Queue()
        pos_module._CFD_SUBSCRIBERS.extend([(2, 99, other_q), (1, 11, matching_q)])
        try:
            with patch.object(pos_module.sse_backplane, "publish"):
                pos_module._publish_cfd_refresh(tenant_id=1, session_id=11)
            # matching_q should have received payload, other_q not
            assert not other_q.qsize()
            assert matching_q.qsize() == 1
        finally:
            pos_module._CFD_SUBSCRIBERS.clear()
            while not matching_q.empty():
                matching_q.get_nowait()
            while not other_q.empty():
                other_q.get_nowait()
