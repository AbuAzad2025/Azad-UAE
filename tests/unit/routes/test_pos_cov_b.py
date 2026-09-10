"""Coverage-targeted POS routes (B) — products fallback, promotions, sessions, shifts.

Targets routes/pos.py uncovered lines 610, 856, 1158, 1161, 1260, 1394, 1396,
1431, 1434 and arcs 1115->1119, 1132->1140, 1262-1264, 1274-1276, 1419-1420,
1443-1444, 1475->1470, 1486-1487.

Real response paths via the Flask test client; mocks only at DB/external
boundaries (tenant queries, write/idempotency services, pricing helpers).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from models.pos_cash_movement import PosCashMovement
from services.idempotency_service import IdempotencyInFlightError
from tests.unit.routes.test_pos_v2_routes import _mock_session, _pos_api_patches


@pytest.fixture
def cov_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


class TestCovBProductsFallbackScope:
    """Line 610: an explicit warehouse_id narrows the fallback stock map."""

    def test_fallback_stock_scoped_to_requested_warehouse(self, cov_client):
        prod = MagicMock(id=21)
        prod.name = "Fallback"
        prod_q = MagicMock()
        prod_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [prod]
        with (
            _pos_api_patches(search_result=([], {}, [])),
            patch("routes.pos.tenant_query", return_value=prod_q),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[3]),
            patch("utils.branching.get_branch_stock_map", return_value={21: 4}) as stock_map,
        ):
            resp = cov_client.get("/pos/api/products?warehouse_id=7")
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1
        assert stock_map.call_args.kwargs["warehouse_ids"] == [7]


class TestCovBPromotionsCustomerTier:
    """Line 856: an active customer resolves its own pricing tier."""

    def test_active_customer_tier_flows_into_evaluation(self, cov_client):
        customer = MagicMock(is_active=True, customer_type="wholesale")
        merged = [
            {
                "product_id": 1,
                "quantity": Decimal("2"),
                "discount_percent": Decimal("0"),
                "unit_price": "12.5",
            }
        ]
        product = MagicMock(id=1, is_active=True, category_id=None)
        evaluation = {"applied": []}
        with (
            _pos_api_patches(merged_lines=merged, tenant_get=lambda m, i, **kw: customer),
            patch(
                "services.pos_write_service.PosWriteService.products_by_ids",
                return_value={1: product},
            ),
            patch(
                "routes.pos.PromotionService.evaluate_cart",
                return_value=evaluation,
            ) as evaluate,
            patch("routes.pos._promotion_evaluation_json", return_value={"ok": True}),
        ):
            resp = cov_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 2}], "customer_id": 8},
            )
        assert resp.status_code == 200
        cart = evaluate.call_args.args[0]
        assert cart[0]["unit_price"] == Decimal("12.500")


class TestCovBSessionOpenLedger:
    """Lines 1158/1161 + arcs 1115->1119/1132->1140: open idempotency ledger."""

    def test_successful_open_completes_idempotency_record(self, cov_client):
        record = MagicMock()
        new_session = _mock_session()
        with (
            _pos_api_patches(session=None, new_session=new_session),
            patch("routes.pos.IdempotencyService.begin", return_value=(record, None)),
            patch("routes.pos.IdempotencyService.complete") as complete,
        ):
            resp = cov_client.post(
                "/pos/api/session/open",
                json={},
                headers={"Idempotency-Key": "open-1"},
            )
        assert resp.status_code == 201
        assert complete.call_args.args[0] is record
        assert complete.call_args.args[2] == 201

    def test_concurrent_open_conflicts_on_duplicate_key(self, cov_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(MagicMock(), None)),
            patch(
                "routes.pos.create_pos_session",
                side_effect=IntegrityError("dup", None, Exception("dup")),
            ),
        ):
            resp = cov_client.post(
                "/pos/api/session/open",
                json={},
                headers={"Idempotency-Key": "open-2"},
            )
        assert resp.status_code == 409

    def test_open_without_branch_or_tenant_context_is_400(self, cov_client, bypass_permission_auth):
        bypass_permission_auth.tenant_id = None
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.get_active_branch_id", return_value=None),
        ):
            resp = cov_client.post("/pos/api/session/open", json={})
        assert resp.status_code == 400


class TestCovBSessionCloseLedger:
    """Line 1260 + arcs 1262-1264/1274-1276: close idempotency ledger."""

    def test_begin_conflict_inside_transaction_is_409(self, cov_client):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.IdempotencyService.replay_if_completed", return_value=None),
            patch(
                "routes.pos.IdempotencyService.begin",
                side_effect=IdempotencyInFlightError,
            ),
        ):
            resp = cov_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "close-err"},
            )
        assert resp.status_code == 409

    def test_stored_response_replays_inside_transaction(self, cov_client):
        session = _mock_session()
        stored = ({"success": True, "session": {"id": 11}}, 200)
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.IdempotencyService.replay_if_completed", return_value=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(None, stored)),
        ):
            resp = cov_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "close-replay"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["meta"]["idempotent_replay"] is True

    def test_integrity_conflict_with_key_is_409(self, cov_client):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.IdempotencyService.replay_if_completed", return_value=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(MagicMock(), None)),
            patch(
                "routes.pos.close_pos_session",
                side_effect=IntegrityError("dup", None, Exception("dup")),
            ),
        ):
            resp = cov_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "close-race"},
            )
        assert resp.status_code == 409

    def test_integrity_failure_without_key_is_500(self, cov_client):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch(
                "routes.pos.close_pos_session",
                side_effect=IntegrityError("dup", None, Exception("dup")),
            ),
        ):
            resp = cov_client.post("/pos/api/session/close", json={"counted_cash": "100"})
        assert resp.status_code == 500


class TestCovBShiftGating:
    """Lines 1394/1431 (feature denied), 1396 (non-JSON), 1434 (no shift)."""

    def test_reconcile_denied_without_shifts_feature(self, cov_client):
        tenant = MagicMock(enable_pos=True, enable_pos_shifts=False)
        with _pos_api_patches(tenant=tenant):
            resp = cov_client.post("/pos/api/shift/reconcile", json={"actual_cash": "10"})
        assert resp.status_code == 403

    def test_reconcile_requires_json_content_type(self, cov_client):
        with _pos_api_patches():
            resp = cov_client.post("/pos/api/shift/reconcile", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_close_denied_without_shifts_feature(self, cov_client):
        tenant = MagicMock(enable_pos=True, enable_pos_shifts=False)
        with _pos_api_patches(tenant=tenant):
            resp = cov_client.post("/pos/api/shift/close", json={})
        assert resp.status_code == 403

    def test_close_without_shift_is_404(self, cov_client):
        with _pos_api_patches(shift=None):
            resp = cov_client.post("/pos/api/shift/close", json={})
        assert resp.status_code == 404


class TestCovBShiftTotals:
    """Arcs 1419-1420/1443-1444 (failures), 1475->1470 (other tender), 1486-1487 (pay-out)."""

    def _shift(self):
        shift = MagicMock(status="open", total_change_given=Decimal("5"))
        shift.session_id = 11
        shift.tenant_id = 1
        shift.to_dict.return_value = {"status": "reconciled"}
        return shift

    def test_reconcile_failure_maps_to_400(self, cov_client):
        shift = self._shift()
        shift.reconcile.side_effect = ValueError("count mismatch")
        with (
            _pos_api_patches(shift=shift),
            patch(
                "services.pos_write_service.PosWriteService.session_sales",
                return_value=[],
            ),
            patch(
                "services.pos_write_service.PosWriteService.shift_cash_movements",
                return_value=[],
            ),
        ):
            resp = cov_client.post("/pos/api/shift/reconcile", json={"actual_cash": "100"})
        assert resp.status_code == 400

    def test_mixed_tenders_and_pay_outs_accumulate(self, cov_client):
        shift = self._shift()
        cash_sale = MagicMock(total_amount=Decimal("100"), payments=[MagicMock(payment_method="cash")])
        card_sale = MagicMock(total_amount=Decimal("40"), payments=[MagicMock(payment_method="card")])
        credit_sale = MagicMock(
            total_amount=Decimal("30"),
            payments=[MagicMock(payment_method="store_credit")],
        )
        pay_in = MagicMock(amount=Decimal("20"), movement_type=PosCashMovement.TYPE_PAY_IN)
        pay_out = MagicMock(amount=Decimal("7"), movement_type=PosCashMovement.TYPE_PAY_OUT)
        with (
            _pos_api_patches(shift=shift),
            patch(
                "services.pos_write_service.PosWriteService.session_sales",
                return_value=[cash_sale, card_sale, credit_sale],
            ),
            patch(
                "services.pos_write_service.PosWriteService.shift_cash_movements",
                return_value=[pay_in, pay_out],
            ),
            patch("routes.pos.payment_amount_base", return_value=Decimal("10")),
        ):
            resp = cov_client.post("/pos/api/shift/reconcile", json={"actual_cash": "100"})
        assert resp.status_code == 200
        assert shift.total_sales == Decimal("170")
        assert shift.total_cash_sales == Decimal("15")
        assert shift.total_card_sales == Decimal("10")
        assert shift.total_pay_ins == Decimal("20")
        assert shift.total_pay_outs == Decimal("7")
        shift.reconcile.assert_called_once_with(Decimal("100"), None)

    def test_close_failure_maps_to_400(self, cov_client):
        shift = MagicMock(status="reconciled")
        shift.to_dict.return_value = {}
        shift.close.side_effect = RuntimeError("db down")
        with _pos_api_patches(shift=shift):
            resp = cov_client.post("/pos/api/shift/close", json={})
        assert resp.status_code == 400
