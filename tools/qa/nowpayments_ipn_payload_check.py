#!/usr/bin/env python3
"""Inspect NOWPayments outbound payloads and webhook idempotency (no provider calls)."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
os.environ.setdefault("BASE_URL", "https://example.com")

from app import create_app

app = create_app()


class TestNOWPaymentsIPNAlignment(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_canonical_ipn_url_helper(self):
        from utils.nowpayments_ipn import get_nowpayments_ipn_url

        self.assertEqual(
            get_nowpayments_ipn_url(),
            "https://example.com/payment-vault/webhook/nowpayments",
        )

    def test_donation_create_payment_payload(self):
        from services.nowpayments_service import NOWPaymentsService

        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(json or {})
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {
                "payment_id": "np-don-1",
                "pay_address": "addr",
                "pay_amount": 1,
                "payment_url": "https://pay.example/1",
            }
            return resp

        with patch("services.nowpayments_service.requests.post", fake_post):
            svc = NOWPaymentsService()
            svc.api_key = "test-key"
            svc.ipn_secret = "secret"
            result = svc.create_payment(
                amount=25,
                order_id="DONATION_42",
                customer_email="d@example.com",
            )
        self.assertTrue(result.get("success"))
        self.assertIn("/payment-vault/webhook/nowpayments", captured["ipn_callback_url"])
        self.assertEqual(captured.get("order_id"), "DONATION_42")

    def test_package_create_payment_payload(self):
        from services.nowpayments_service import NOWPaymentsService

        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(json or {})
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {
                "payment_id": "np-pkg-1",
                "pay_address": "addr",
                "pay_amount": 1,
                "payment_url": "https://pay.example/pkg",
            }
            return resp

        with patch("services.nowpayments_service.requests.post", fake_post):
            svc = NOWPaymentsService()
            svc.api_key = "test-key"
            svc.ipn_secret = "secret"
            result = svc.create_payment(
                amount=99,
                order_id="PURCHASE_5",
                customer_email="buyer@example.com",
                transaction_type="purchase",
            )
        self.assertTrue(result.get("success"))
        self.assertIn("/payment-vault/webhook/nowpayments", captured["ipn_callback_url"])
        self.assertEqual(captured.get("order_id"), "PURCHASE_5")

    def test_store_create_payment_payload(self):
        from services.store_online_payment_service import StoreOnlinePaymentService

        sale = MagicMock()
        sale.id = 200
        sale.total_amount = 150
        sale.currency = "AED"
        sale.sale_number = "SO-200"
        sale.checkout_gateway_ref = None
        sale.checkout_payment_method = None

        store = MagicMock()
        store.tenant_id = 2
        store.title = "Demo Shop"

        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(json or {})
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {
                "payment_id": "np-store-1",
                "payment_url": "https://pay.example/store",
            }
            return resp

        with patch("services.store_online_payment_service.requests.post", fake_post):
            with patch.object(StoreOnlinePaymentService, "_api_key", return_value="k"):
                with patch("services.store_online_payment_service.db.session.commit"):
                    StoreOnlinePaymentService.create_payment_for_sale(
                        sale, store, customer_email="s@example.com"
                    )

        self.assertIn("/payment-vault/webhook/nowpayments", captured["ipn_callback_url"])
        self.assertEqual(captured.get("order_id"), "STORE_200_2")

    def test_webhook_donation_idempotent(self):
        from services.webhook_service import WebhookService

        donation = MagicMock()
        donation.status = "completed"
        donation.id = 1

        with patch(
            "services.webhook_service.Donation.query"
        ) as q:
            q.filter.return_value.first.return_value = donation
            out = WebhookService._process_donation_webhook(
                {"payment_id": "np-1", "payment_status": "finished"}
            )
        self.assertTrue(out["success"])
        self.assertIn("idempotent", out["message"])

    def test_webhook_purchase_idempotent(self):
        from services.webhook_service import WebhookService

        purchase = MagicMock()
        purchase.payment_status = "completed"
        purchase.activation_status = "activated"
        purchase.id = 5

        with patch("services.webhook_service.PackagePurchase.query") as q:
            q.filter_by.return_value.first.return_value = purchase
            out = WebhookService._process_purchase_webhook(
                {"payment_id": "np-2", "payment_status": "finished"}
            )
        self.assertTrue(out["success"])
        self.assertIn("idempotent", out["message"])

    def test_webhook_store_idempotent(self):
        from services.webhook_service import WebhookService

        sale = MagicMock()
        sale.status = "confirmed"
        sale.sale_number = "SO-1"
        sale.checkout_gateway_ref = "np-3"

        with patch(
            "services.store_online_payment_service.StoreOnlinePaymentService.parse_store_order_id",
            return_value=(1, 2),
        ):
            with patch("models.Sale") as Sale:
                Sale.query.filter_by.return_value.first.return_value = sale
                out = WebhookService._process_store_order_webhook(
                    {
                        "payment_id": "np-3",
                        "payment_status": "finished",
                        "order_id": "STORE_1_2",
                    }
                )
        self.assertTrue(out["success"])
        self.assertIn("idempotent", out["message"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestNOWPaymentsIPNAlignment)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
