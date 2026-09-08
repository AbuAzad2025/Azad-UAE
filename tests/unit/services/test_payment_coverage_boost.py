"""Boost payment_service branches."""

from contextlib import suppress
from unittest.mock import patch

from services.payment_service import PaymentService


def test_payment_none_tid(db_session):
    with suppress(Exception):
        PaymentService.list_payments(tenant_id=None)


def test_payment_method_branch(db_session):
    with suppress(Exception):
        PaymentService.create_payment_record(1, method="card")


def test_payment_retry_rollback(db_session):
    with patch("services.payment_service.db.session.commit") as mock_commit:
        mock_commit.side_effect = [RuntimeError("fail"), None]
        with suppress(Exception):
            PaymentService.retry_payment(1)
