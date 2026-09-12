"""Cov5: webhook_service — unknown-status and non-pending refund arcs."""

from __future__ import annotations

from datetime import datetime as dt
from decimal import Decimal
from unittest.mock import patch as _patch


def _sale(db_session, sample_tenant, sample_customer, sample_user, sample_warehouse, status):
    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number=f"STORE-COV5-{status}",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=sample_warehouse.id,
        sale_date=dt.now(),
        source="online_store",
        status=status,
        subtotal=Decimal("10"),
        total_amount=Decimal("10"),
        amount=Decimal("10"),
        amount_aed=Decimal("10"),
    )
    db_session.add(sale)
    db_session.flush()
    return sale


def test_unknown_payment_status_acks(db_session, sample_tenant, sample_customer, sample_user, sample_warehouse):
    from services.webhook_service import WebhookService

    sale = _sale(db_session, sample_tenant, sample_customer, sample_user, sample_warehouse, "pending")
    with _patch(
        "services.store_online_payment_service.StoreOnlinePaymentService.parse_store_order_id",
        return_value=(sale.id, sample_tenant.id),
    ):
        out = WebhookService._process_store_order_webhook(
            {"payment_id": "gw-1", "payment_status": "waiting", "order_id": f"STORE_{sale.id}_{sample_tenant.id}"}
        )
        assert out == {"success": True, "message": "Store order updated to waiting"}


def test_refund_non_pending_skips_cancel(
    db_session, sample_tenant, sample_customer, sample_user, sample_warehouse
):
    from services.webhook_service import WebhookService

    sale = _sale(db_session, sample_tenant, sample_customer, sample_user, sample_warehouse, "confirmed")
    with (
        _patch(
            "services.store_online_payment_service.StoreOnlinePaymentService.parse_store_order_id",
            return_value=(sale.id, sample_tenant.id),
        ),
        _patch("services.store_order_service.StoreOrderService.cancel_order") as cancel,
    ):
        out = WebhookService._process_store_order_webhook(
            {"payment_id": "gw-1", "payment_status": "refunded", "order_id": f"STORE_{sale.id}_{sample_tenant.id}"}
        )
        assert out["success"] is True
        cancel.assert_not_called()
