"""POS Phase 4 route tests — receipt lookup (smart RMA), POS returns with
cash/credit refunds, cross-branch stock lookup, SaaS sub-feature gating, and
offline-first idempotency. Mocked at the route boundary per convention.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
)
from tests.unit.routes.test_pos_v2_routes import (
    _pos_api_patches,
)


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


def _feature_tenant(**overrides):
    tenant = MagicMock()
    tenant.enable_pos = True
    tenant.subscription_plan = overrides.pop("subscription_plan", "pro")
    tenant.enable_pos_promotions = overrides.pop("enable_pos_promotions", True)
    tenant.enable_pos_multi_tender = overrides.pop("enable_pos_multi_tender", True)
    tenant.enable_pos_returns = overrides.pop("enable_pos_returns", True)
    tenant.enable_pos_shifts = overrides.pop("enable_pos_shifts", True)
    return tenant


def _product_return_mock():
    product_return = MagicMock()
    product_return.id = 77
    product_return.return_number = "R-100"
    product_return.refund_amount = Decimal("50")
    product_return.currency = "AED"
    product_return.exchange_rate = Decimal("1")
    product_return.amount_aed = Decimal("50")
    return product_return


def _checkout_sale_mock():
    return MagicMock(
        id=100,
        sale_number="S-100",
        tenant_id=1,
        total_amount=Decimal("50"),
    )


class TestReceiptLookup:
    def test_found(self, pos_client):
        receipt = {"sale_id": 55, "sale_number": "S-1", "lines": []}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.lookup_receipt", return_value=receipt) as lookup,
        ):
            resp = pos_client.get("/pos/api/receipts/lookup?number=S-1")
        assert resp.status_code == 200
        assert resp.get_json()["receipt"]["sale_id"] == 55
        lookup.assert_called_once()

    def test_not_found_404(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.lookup_receipt", return_value=None),
        ):
            resp = pos_client.get("/pos/api/receipts/lookup?number=NOPE")
        assert resp.status_code == 404

    def test_barcode_param_accepted(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.lookup_receipt", return_value={"sale_id": 1}) as lookup,
        ):
            resp = pos_client.get("/pos/api/receipts/lookup?barcode=S-9")
        assert resp.status_code == 200
        assert lookup.call_args.args[1] == "S-9"

    def test_feature_denied_on_basic_tenant(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_returns=None)
        with (
            _pos_api_patches(tenant=tenant),
            patch("routes.pos.PosRmaService.lookup_receipt") as lookup,
        ):
            resp = pos_client.get("/pos/api/receipts/lookup?number=S-1")
        assert resp.status_code == 403
        assert resp.get_json()["feature"] == "pos_returns"
        lookup.assert_not_called()

    def test_permission_gated(self, pos_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with (
            patch("utils.decorators.is_global_owner_user", return_value=False),
            _pos_api_patches(),
        ):
            resp = pos_client.get("/pos/api/receipts/lookup?number=S-1")
        assert resp.status_code == 403


class TestPosReturns:
    _PAYLOAD = {"sale_id": 55, "lines": [{"sale_line_id": 201, "quantity": 1, "condition": "good"}]}

    def test_credit_refund_default(self, pos_client):
        product_return = _product_return_mock()
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=55),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                return_value=(product_return, None),
            ) as create,
        ):
            resp = pos_client.post("/pos/api/returns", json=self._PAYLOAD)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["return_number"] == "R-100"
        assert data["refund_method"] == "credit"
        assert data["refund_payment_number"] is None
        assert create.call_args.kwargs["refund_method"] == "credit"

    def test_cash_refund_returns_payment_number(self, pos_client):
        product_return = _product_return_mock()
        payment = MagicMock(payment_number="PAY-500")
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=55),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                return_value=(product_return, payment),
            ),
        ):
            resp = pos_client.post("/pos/api/returns", json={**self._PAYLOAD, "refund_method": "cash"})
        assert resp.status_code == 201
        assert resp.get_json()["refund_payment_number"] == "PAY-500"

    def test_sale_not_found_404(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=None),
        ):
            resp = pos_client.post("/pos/api/returns", json=self._PAYLOAD)
        assert resp.status_code == 404

    def test_over_return_blocked_400(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=55),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                side_effect=ValueError("Cannot return 5. Already returned: 4, Sold: 4."),
            ),
        ):
            resp = pos_client.post("/pos/api/returns", json=self._PAYLOAD)
        assert resp.status_code == 400

    def test_feature_denied_on_basic_tenant(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_returns=None)
        with (
            _pos_api_patches(tenant=tenant),
            patch("routes.pos.PosRmaService.create_pos_return") as create,
        ):
            resp = pos_client.post("/pos/api/returns", json=self._PAYLOAD)
        assert resp.status_code == 403
        create.assert_not_called()

    def test_empty_lines_400(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/returns", json={"sale_id": 55, "lines": []})
        assert resp.status_code == 400

    def test_requires_open_session(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post("/pos/api/returns", json=self._PAYLOAD)
        assert resp.status_code == 403


class TestStockLookup:
    def test_per_warehouse_breakdown(self, pos_client):
        result = {
            "product_id": 11,
            "product_name": "Widget",
            "total_on_hand": 10.0,
            "warehouses": [
                {"warehouse_id": 1, "warehouse_name": "Main", "branch_id": 2, "on_hand": 7.0},
                {"warehouse_id": 2, "warehouse_name": "Branch", "branch_id": 3, "on_hand": 3.0},
            ],
        }
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.stock_breakdown", return_value=result),
        ):
            resp = pos_client.get("/pos/api/stock/lookup?product_id=11")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_on_hand"] == 10.0
        assert len(data["warehouses"]) == 2

    def test_barcode_lookup(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.stock_breakdown", return_value={"product_id": 11}) as breakdown,
        ):
            resp = pos_client.get("/pos/api/stock/lookup?barcode=BC11")
        assert resp.status_code == 200
        assert breakdown.call_args.kwargs["barcode"] == "BC11"

    def test_not_found_404(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.stock_breakdown", return_value=None),
        ):
            resp = pos_client.get("/pos/api/stock/lookup?product_id=999")
        assert resp.status_code == 404

    def test_missing_identifier_400(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/stock/lookup")
        assert resp.status_code == 400


class TestFeatureFlagGating:
    _CHECKOUT_PAYLOAD = {"lines": [{"product_id": 1, "quantity": 1}], "quick_customer": True}

    def test_promotions_evaluate_denied_on_basic(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_promotions=None)
        with _pos_api_patches(tenant=tenant):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 403
        assert resp.get_json()["feature"] == "pos_promotions"

    def test_promotions_evaluate_allowed_on_pro(self, pos_client):
        from tests.unit.routes.test_pos_v2_routes import _mock_product

        session_mock = MagicMock()
        session_mock.get.return_value = _feature_tenant(subscription_plan="pro")
        query = MagicMock()
        query.filter.return_value.all.return_value = [_mock_product()]
        query.filter.return_value.with_for_update.return_value.all.return_value = [_mock_product()]
        session_mock.query.side_effect = lambda model: query

        evaluation = {
            "lines": [],
            "subtotal_before": Decimal("0"),
            "total_discount": Decimal("0"),
            "subtotal_after": Decimal("0"),
            "applied_rules": [],
            "upsell_prompts": [],
        }
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session", session_mock),
            patch("routes.pos.PromotionService.evaluate_cart", return_value=evaluation),
        ):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 200

    def test_split_tender_denied_on_basic(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_multi_tender=None)
        payload = {
            **self._CHECKOUT_PAYLOAD,
            "payments": [
                {"amount": 30, "payment_method": "cash"},
                {"amount": 20, "payment_method": "card"},
            ],
        }
        with _pos_api_patches(tenant=tenant):
            resp = pos_client.post("/pos/api/checkout", json=payload)
        assert resp.status_code == 403
        assert resp.get_json()["feature"] == "pos_multi_tender"

    def test_split_tender_allowed_on_pro(self, pos_client):
        payload = {
            **self._CHECKOUT_PAYLOAD,
            "payments": [
                {"amount": 30, "payment_method": "cash"},
                {"amount": 20, "payment_method": "card"},
            ],
        }
        with _pos_api_patches(tenant=_feature_tenant(subscription_plan="pro")):
            resp = pos_client.post("/pos/api/checkout", json=payload)
        assert resp.status_code == 200

    def test_cash_movements_denied_on_basic(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_shifts=None)
        with _pos_api_patches(tenant=tenant):
            resp = pos_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_out", "amount": 10, "reason": "test"},
            )
        assert resp.status_code == 403
        assert resp.get_json()["feature"] == "pos_shifts"

    def test_core_checkout_works_on_basic_without_shift(self, pos_client):
        """Basic tier: shiftless core checkout must stay available."""
        tenant = _feature_tenant(
            subscription_plan="basic",
            enable_pos_promotions=False,
            enable_pos_multi_tender=False,
            enable_pos_returns=False,
            enable_pos_shifts=False,
        )
        no_shift_q = MagicMock()
        no_shift_q.filter.return_value.order_by.return_value.first.return_value = None
        for m in ("filter", "filter_by", "order_by"):
            getattr(no_shift_q, m).return_value = no_shift_q
        with (
            _pos_api_patches(tenant=tenant),
            patch("routes.pos.PosShift.query", no_shift_q),
        ):
            resp = pos_client.post("/pos/api/checkout", json=self._CHECKOUT_PAYLOAD)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_shift_open_denied_on_basic(self, pos_client):
        tenant = _feature_tenant(subscription_plan="basic", enable_pos_shifts=None)
        with _pos_api_patches(tenant=tenant):
            resp = pos_client.post("/pos/api/shift/open", json={"starting_cash": 100})
        assert resp.status_code == 403


class TestCheckoutIdempotency:
    _PAYLOAD = {"lines": [{"product_id": 1, "quantity": 1}], "quick_customer": True}

    def test_duplicate_key_replays_without_second_sale(self, pos_client):
        record = MagicMock()
        stored = ({"success": True, "sale_id": 100, "sale_number": "S-100"}, 200)
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.IdempotencyService.begin",
                side_effect=[(record, None), (None, stored)],
            ) as begin,
            patch("routes.pos.IdempotencyService.complete") as complete,
            patch("routes.pos.hash_request_payload", return_value="h"),
            patch("routes.pos.SaleService.create_sale", return_value=_checkout_sale_mock()) as create_sale,
        ):
            first = pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "abc"})
            second = pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "abc"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.get_json()["idempotent_replay"] is True
        create_sale.assert_called_once()
        complete.assert_called_once()
        assert begin.call_count == 2

    def test_different_key_executes_again(self, pos_client):
        record = MagicMock()
        with (
            _pos_api_patches(),
            patch("routes.pos.IdempotencyService.begin", return_value=(record, None)),
            patch("routes.pos.IdempotencyService.complete"),
            patch("routes.pos.hash_request_payload", return_value="h"),
            patch("routes.pos.SaleService.create_sale", return_value=_checkout_sale_mock()) as create_sale,
        ):
            pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "k1"})
            pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "k2"})
        assert create_sale.call_count == 2

    def test_in_flight_duplicate_409(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.IdempotencyService.begin",
                side_effect=IdempotencyInFlightError("in progress"),
            ),
            patch("routes.pos.hash_request_payload", return_value="h"),
        ):
            resp = pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "abc"})
        assert resp.status_code == 409

    def test_hash_mismatch_422(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.IdempotencyService.begin",
                side_effect=IdempotencyHashMismatchError("mismatch"),
            ),
            patch("routes.pos.hash_request_payload", return_value="h"),
        ):
            resp = pos_client.post("/pos/api/checkout", json=self._PAYLOAD, headers={"Idempotency-Key": "abc"})
        assert resp.status_code == 422

    def test_body_key_accepted(self, pos_client):
        record = MagicMock()
        with (
            _pos_api_patches(),
            patch("routes.pos.IdempotencyService.begin", return_value=(record, None)) as begin,
            patch("routes.pos.IdempotencyService.complete"),
            patch("routes.pos.hash_request_payload", return_value="h"),
        ):
            resp = pos_client.post("/pos/api/checkout", json={**self._PAYLOAD, "idempotency_key": "body-key"})
        assert resp.status_code == 200
        assert begin.call_args.kwargs["key"] == "body-key"


class TestReturnsIdempotency:
    _PAYLOAD = {"sale_id": 55, "lines": [{"sale_line_id": 201, "quantity": 1}]}

    def test_duplicate_return_replays(self, pos_client):
        record = MagicMock()
        stored = ({"success": True, "return_number": "R-100"}, 201)
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=55),
            patch(
                "routes.pos.IdempotencyService.begin",
                side_effect=[(record, None), (None, stored)],
            ),
            patch("routes.pos.IdempotencyService.complete"),
            patch("routes.pos.hash_request_payload", return_value="h"),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                return_value=(_product_return_mock(), None),
            ) as create,
        ):
            first = pos_client.post("/pos/api/returns", json=self._PAYLOAD, headers={"Idempotency-Key": "r1"})
            second = pos_client.post("/pos/api/returns", json=self._PAYLOAD, headers={"Idempotency-Key": "r1"})
        assert first.status_code == 201
        assert second.status_code == 201
        assert second.get_json()["idempotent_replay"] is True
        create.assert_called_once()
