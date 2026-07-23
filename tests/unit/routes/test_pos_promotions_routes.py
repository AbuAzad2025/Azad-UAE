"""POS promotions — evaluate endpoint + checkout integration (mocked at boundary)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import unauthenticated_client
from tests.unit.routes.test_pos_v2_routes import (
    _mock_product,
    _pos_api_patches,
    _pos_enabled_patches,
)


def _evaluation(total="5.000", rules=None, prompts=None):
    rules = rules if rules is not None else [
        {
            "campaign_id": 7,
            "name": "Bundle Deal",
            "campaign_type": "bundle",
            "discount_amount": Decimal(total),
        }
    ]
    return {
        "lines": [
            {
                "product_id": 1,
                "quantity": Decimal("2"),
                "unit_price": Decimal("50"),
                "original_total": Decimal("100"),
                "discount_amount": Decimal(total),
                "adjusted_total": Decimal("100") - Decimal(total),
            }
        ],
        "subtotal_before": Decimal("100"),
        "total_discount": Decimal(total),
        "subtotal_after": Decimal("100") - Decimal(total),
        "applied_rules": rules,
        "upsell_prompts": prompts
        if prompts is not None
        else [
            {
                "type": "bundle",
                "campaign_id": 7,
                "campaign_name": "Bundle Deal",
                "product_id": 1,
                "needed_quantity": "1",
                "needed_amount": None,
                "message": "أضف 1 قطعة إضافية للحصول على سعر العرض.",
            }
        ],
    }


def _products_session(products):
    session_mock = MagicMock()
    session_mock.get.return_value = MagicMock(enable_pos=True)

    def _query_side(model):
        q = MagicMock()
        q.filter.return_value.all.return_value = products
        q.filter.return_value.with_for_update.return_value.all.return_value = products
        return q

    session_mock.query.side_effect = _query_side
    return session_mock


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


class TestPromotionEvaluateEndpoint:
    def test_requires_json(self, pos_client):
        with _pos_enabled_patches():
            resp = pos_client.post("/pos/api/promotions/evaluate", data="not-json")
        assert resp.status_code == 415

    def test_requires_login(self, pos_client):
        with _pos_enabled_patches(), unauthenticated_client(pos_client):
            resp = pos_client.post("/pos/api/promotions/evaluate", json={"lines": []})
        assert resp.status_code == 401

    def test_empty_lines(self, pos_client):
        with _pos_enabled_patches():
            resp = pos_client.post("/pos/api/promotions/evaluate", json={"lines": []})
        assert resp.status_code == 400

    def test_invalid_lines(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.merge_checkout_lines", side_effect=ValueError("bad")),
        ):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 400

    def test_invalid_product(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session", _products_session([])),
        ):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 400

    def test_success_returns_priced_cart_and_upsell(self, pos_client):
        product = _mock_product()
        evaluation = _evaluation()
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session", _products_session([product])),
            patch("routes.pos.PromotionService.evaluate_cart", return_value=evaluation) as evaluate,
        ):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 2}]},
            )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["total_discount"] == 5.0
        assert data["subtotal_after"] == 95.0
        assert data["applied_rules"][0]["campaign_type"] == "bundle"
        assert data["upsell_prompts"][0]["needed_quantity"] == "1"
        assert data["lines"][0]["adjusted_total"] == 95.0
        # Engine received the tier-priced, tenant-scoped cart
        evaluate.assert_called_once()
        cart = evaluate.call_args.args[0]
        assert cart[0]["product_id"] == 1
        assert cart[0]["unit_price"] == Decimal("50.000")

    def test_engine_value_error_returns_400(self, pos_client):
        product = _mock_product()
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session", _products_session([product])),
            patch("routes.pos.PromotionService.evaluate_cart", side_effect=ValueError("bad cart")),
        ):
            resp = pos_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 400


class TestCheckoutPromotionIntegration:
    @staticmethod
    def _checkout_payload(**extra):
        base = {
            "quick_customer": True,
            "lines": [{"product_id": 1, "quantity": 1}],
            "payment_method": "cash",
            "paid_amount": 50,
        }
        base.update(extra)
        return base

    def test_checkout_passes_evaluation_to_sale_service(self, pos_client):
        evaluation = _evaluation()
        with (
            _pos_api_patches(),
            patch("routes.pos.PromotionService.evaluate_cart", return_value=evaluation),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100, sale_number="S-100", tenant_id=1, total_amount=Decimal("45")
            )
            resp = pos_client.post("/pos/api/checkout", json=self._checkout_payload())
        data = resp.get_json()
        assert data["success"] is True
        assert create_sale.call_args.kwargs["promotion_evaluation"] is evaluation
        assert data["promotion_discount"] == 5.0
        assert data["promotions_applied"][0]["name"] == "Bundle Deal"
        assert data["upsell_prompts"][0]["type"] == "bundle"

    def test_checkout_uses_tier_aware_pricing_for_lines(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100, sale_number="S-100", tenant_id=1, total_amount=Decimal("50")
            )
            resp = pos_client.post("/pos/api/checkout", json=self._checkout_payload())
        assert resp.get_json()["success"] is True
        lines_data = create_sale.call_args.kwargs["lines_data"]
        # No explicit price in payload → priced via PricingService (regular_price 50)
        assert lines_data[0]["unit_price"] == Decimal("50.000")

    def test_checkout_survives_promotion_engine_failure(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PromotionService.evaluate_cart", side_effect=RuntimeError("boom")),
            patch("routes.pos.SaleService.create_sale") as create_sale,
        ):
            create_sale.return_value = MagicMock(
                id=100, sale_number="S-100", tenant_id=1, total_amount=Decimal("50")
            )
            resp = pos_client.post("/pos/api/checkout", json=self._checkout_payload())
        data = resp.get_json()
        assert data["success"] is True
        assert create_sale.call_args.kwargs["promotion_evaluation"] is None
        assert data["promotion_discount"] == 0.0
        assert data["promotions_applied"] == []
        assert data["upsell_prompts"] == []

    def test_checkout_manual_price_override_still_guarded(self, pos_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_owner = False
        merged = [
            {
                "product_id": 1,
                "quantity": Decimal("1"),
                "discount_percent": Decimal("0"),
                "unit_price": Decimal("30"),
            }
        ]
        with (
            _pos_api_patches(),
            patch("routes.pos.merge_checkout_lines", return_value=merged),
        ):
            resp = pos_client.post("/pos/api/checkout", json=self._checkout_payload())
        assert resp.status_code == 403
