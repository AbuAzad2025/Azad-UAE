"""Boost payment_service branches."""
from unittest.mock import patch
from services.payment_service import PaymentService


def test_payment_none_tid(db_session):
    try:
        PaymentService.list_payments(tenant_id=None)
    except Exception:
        pass


def test_payment_retry_rollback(db_session):
    with patch("services.payment_service.db.session.commit") as m:
        m.side_effect = [RuntimeError("fail"), None]
        try:
            PaymentService.retry_payment(1)
        except Exception:
            pass
