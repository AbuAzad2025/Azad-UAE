"""POS Phase 2 route tests — parked carts, split tenders, fast cash.

Mocked at the route boundary per convention: PosCartService / SaleService /
PosCartService collaborators are patched; request→response contracts are
asserted against real route code.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.pos_cart_service import PosCartConflictError
from tests.unit.routes.test_pos_v2_routes import (
    _mock_session,
    _pos_api_patches,
)


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


def _cart_mock(summary=None, detail=None):
    cart = MagicMock()
    cart.to_summary_dict.return_value = summary or {
        "id": 5,
        "label": "طاولة ٥",
        "status": "parked",
        "item_count": 2,
        "total_estimate": 59.0,
        "currency": "AED",
    }
    cart.to_detail_dict.return_value = detail or {
        "id": 5,
        "label": "طاولة ٥",
        "status": "resumed",
        "item_count": 2,
        "total_estimate": 59.0,
        "currency": "AED",
        "payload": {"lines": [{"product_id": 1, "quantity": "2", "unit_price": "25"}]},
    }
    return cart


class TestParkedCartRoutes:
    def test_list_returns_summaries(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.list_carts", return_value=[_cart_mock()]) as list_carts,
        ):
            resp = pos_client.get("/pos/api/carts")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["carts"][0]["id"] == 5
        assert "payload" not in data["carts"][0]
        list_carts.assert_called_once()

    def test_list_empty_without_session(self, pos_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.PosCartService.list_carts", return_value=[]),
        ):
            resp = pos_client.get("/pos/api/carts")
        assert resp.get_json()["carts"] == []

    def test_park_success(self, pos_client):
        payload = {"lines": [{"product_id": 1, "quantity": "2", "unit_price": "25"}]}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.park_cart", return_value=_cart_mock()) as park_cart,
        ):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": payload, "label": "طاولة ٥"})
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["cart"]["label"] == "طاولة ٥"
        assert park_cart.call_args.kwargs["payload"] == payload
        assert park_cart.call_args.kwargs["label"] == "طاولة ٥"

    def test_park_requires_json(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/carts/park", data="not-json")
        assert resp.status_code == 415

    def test_park_requires_open_session(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": {"lines": []}})
        assert resp.status_code == 403

    def test_park_invalid_payload(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosCartService.park_cart",
                side_effect=ValueError("لا يمكن ركن سلة فارغة — أضف منتجات أولاً."),
            ),
        ):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": {"lines": []}})
        assert resp.status_code == 400

    def test_park_update_missing_cart(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.park_cart", side_effect=LookupError("السلة غير موجودة.")),
        ):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": {"lines": []}, "cart_id": 99})
        assert resp.status_code == 404

    def test_retrieve_resumes_and_returns_payload(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.resume_cart", return_value=_cart_mock()),
        ):
            resp = pos_client.get("/pos/api/carts/5")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["cart"]["payload"]["lines"][0]["product_id"] == 1

    def test_retrieve_double_resume_conflict(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosCartService.resume_cart",
                side_effect=PosCartConflictError("تم استرجاع هذه السلة مسبقاً."),
            ),
        ):
            resp = pos_client.get("/pos/api/carts/5")
        assert resp.status_code == 409

    def test_retrieve_cross_tenant_not_found(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.resume_cart", side_effect=LookupError("السلة غير موجودة.")),
        ):
            resp = pos_client.get("/pos/api/carts/777")
        assert resp.status_code == 404

    def test_delete_success(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.delete_cart") as delete_cart,
        ):
            resp = pos_client.delete("/pos/api/carts/5")
        assert resp.get_json()["success"] is True
        delete_cart.assert_called_once()

    def test_delete_missing(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCartService.delete_cart", side_effect=LookupError("السلة غير موجودة.")),
        ):
            resp = pos_client.delete("/pos/api/carts/999")
        assert resp.status_code == 404


class TestFastCashRoute:
    def test_fast_cash_aed(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/fast-cash?total=37&currency=AED")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["currency"] == "AED"
        amounts = [o["amount"] for o in data["options"]]
        assert amounts == [37.0, 40.0, 50.0, 100.0, 200.0, 500.0, 1000.0]
        assert data["options"][0]["is_exact"] is True
        assert data["options"][0]["change"] == 0.0
        assert data["options"][1]["change"] == 3.0

    def test_fast_cash_default_currency_from_tenant(self, pos_client):
        with (
            _pos_api_patches(),
            patch("utils.currency_utils.get_tenant_base_currency", return_value="AED"),
        ):
            resp = pos_client.get("/pos/api/fast-cash?total=10")
        data = resp.get_json()
        assert data["currency"] == "AED"
        assert data["options"][0]["amount"] == 10.0

    def test_fast_cash_missing_total(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/fast-cash")
        assert resp.status_code == 400

    def test_fast_cash_invalid_total(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/fast-cash?total=abc")
        assert resp.status_code == 400

    def test_fast_cash_negative_total(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/fast-cash?total=-5")
        assert resp.status_code == 400

    def test_fast_cash_change_exactness(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/fast-cash?total=7.555&currency=AED")
        data = resp.get_json()
        by_amount = {o["amount"]: o["change"] for o in data["options"]}
        assert by_amount[10.0] == 2.445


class TestSplitTenderCheckout:
    @staticmethod
    def _payload(**extra):
        base = {
            "quick_customer": True,
            "lines": [{"product_id": 1, "quantity": 1}],
            "payments": [
                {"amount": "30", "payment_method": "cash"},
                {"amount": "20", "payment_method": "card"},
            ],
        }
        base.update(extra)
        return base

    def test_split_payments_reach_sale_service(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
                amount_aed=Decimal("50"),
                payment_status="paid",
            )
            resp = pos_client.post("/pos/api/checkout", json=self._payload())
        data = resp.get_json()
        assert data["success"] is True
        kwargs = create_sale.call_args.kwargs
        assert kwargs["payment_data"] is None
        payments = kwargs["payments_data"]
        assert len(payments) == 2
        assert payments[0]["amount"] == Decimal("30")
        assert payments[0]["payment_method"] == "cash"
        assert payments[0]["currency"] == "AED"
        assert payments[1]["payment_method"] == "card"
        assert data["tenders"] == [
            {"method": "cash", "amount": 30.0, "currency": "AED"},
            {"method": "card", "amount": 20.0, "currency": "AED"},
        ]
        assert data["payment_status"] == "paid"
        assert data["change_due"] == 0.0

    def test_payments_array_takes_precedence_over_legacy_fields(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
            )
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(paid_amount=50, payment_method="cash"),
            )
        assert resp.get_json()["success"] is True
        kwargs = create_sale.call_args.kwargs
        assert kwargs["payment_data"] is None
        assert kwargs["payments_data"] is not None

    def test_legacy_single_payment_still_works(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
            )
            resp = pos_client.post(
                "/pos/api/checkout",
                json={
                    "quick_customer": True,
                    "lines": [{"product_id": 1, "quantity": 1}],
                    "payment_method": "cash",
                    "paid_amount": 50,
                },
            )
        assert resp.get_json()["success"] is True
        kwargs = create_sale.call_args.kwargs
        assert kwargs["payments_data"] is None
        assert kwargs["payment_data"]["payment_method"] == "cash"
        assert kwargs["payment_data"]["amount"] == 50.0

    def test_session_totals_accumulate_per_tender(self, pos_client):
        session = _mock_session()
        with _pos_api_patches(session=session):
            resp = pos_client.post("/pos/api/checkout", json=self._payload())
        assert resp.get_json()["success"] is True
        assert session.total_cash_sales == Decimal("30.000")
        assert session.total_card_sales == Decimal("20.000")
        assert session.total_sales == Decimal("50")

    def test_change_due_reported_for_cash_overpay(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
                amount_aed=Decimal("50"),
                payment_status="paid",
            )
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(payments=[{"amount": "100", "payment_method": "cash"}]),
            )
        assert resp.get_json()["change_due"] == 50.0

    def test_no_change_due_for_card_overpay(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
                amount_aed=Decimal("50"),
                payment_status="paid",
            )
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(payments=[{"amount": "100", "payment_method": "card"}]),
            )
        assert resp.get_json()["change_due"] == 0.0

    def test_empty_payments_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/checkout", json=self._payload(payments=[]))
        assert resp.status_code == 400

    def test_non_list_payments_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/checkout", json=self._payload(payments="cash"))
        assert resp.status_code == 400

    def test_zero_chunk_amount_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(payments=[{"amount": "0", "payment_method": "cash"}]),
            )
        assert resp.status_code == 400

    def test_invalid_chunk_amount_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(payments=[{"amount": "abc", "payment_method": "cash"}]),
            )
        assert resp.status_code == 400

    def test_missing_chunk_method_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(payments=[{"amount": "30"}]),
            )
        assert resp.status_code == 400

    def test_non_dict_chunk_rejected(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/checkout", json=self._payload(payments=["cash"]))
        assert resp.status_code == 400

    def test_mixed_currency_chunks_keep_own_rate(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100,
                sale_number="S-100",
                tenant_id=1,
                total_amount=Decimal("50"),
            )
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._payload(
                    payments=[
                        {"amount": "10", "payment_method": "cash", "currency": "USD", "exchange_rate": "3.673"},
                        {"amount": "13.27", "payment_method": "card"},
                    ]
                ),
            )
        assert resp.get_json()["success"] is True
        payments = create_sale.call_args.kwargs["payments_data"]
        assert payments[0]["currency"] == "USD"
        assert payments[0]["exchange_rate"] == Decimal("3.673")
        assert payments[1]["currency"] == "AED"
