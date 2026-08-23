"""Audit-row persistence for hard-delete ORM events (models/events.py → audit_logs).

The delete listeners are registered globally by the app factory; these tests
prove real ORM deletes write audit_logs rows (tenant-aware) and that listener
failures are isolated from the request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _app_ctx(app):
    with app.app_context():
        yield


class TestSaleDeleteAuditRow:
    def test_delete_writes_tenant_scoped_audit_row(self, db_session, sample_sale):
        from models import AuditLog

        sale_id, tenant_id, sale_number = sample_sale.id, sample_sale.tenant_id, sample_sale.sale_number

        db_session.delete(sample_sale)
        db_session.flush()

        row = (
            AuditLog.query.filter_by(action="delete", table_name="sales", record_id=sale_id)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.tenant_id == tenant_id
        assert row.changes and row.changes.get("label") == sale_number

    def test_file_logging_still_fires_alongside_audit_row(self, db_session, sample_sale, mocker):
        from models import AuditLog

        warn = mocker.patch("models.events.logger.warning")
        sale_id = sample_sale.id

        db_session.delete(sample_sale)
        db_session.flush()

        assert warn.called
        assert AuditLog.query.filter_by(action="delete", table_name="sales", record_id=sale_id).count() >= 1


class TestReceiptDeleteAuditRow:
    def test_receipt_delete_writes_audit_row(self, db_session, sample_tenant, sample_customer):
        from models import AuditLog
        from models.receipt import Receipt

        receipt = Receipt(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            receipt_number=f"RCV-AUD-{datetime.now(UTC).timestamp()}",
            receipt_date=datetime.now(UTC),
            amount_aed=Decimal("25.000"),
            amount=Decimal("25.000"),
            currency="AED",
            exchange_rate=1,
            payment_method="cash",
            payment_confirmed=True,
        )
        db_session.add(receipt)
        db_session.flush()
        receipt_id, tenant_id = receipt.id, receipt.tenant_id

        db_session.delete(receipt)
        db_session.flush()

        row = (
            AuditLog.query.filter_by(action="delete", table_name="receipts", record_id=receipt_id)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.tenant_id == tenant_id
        assert row.changes and row.changes["label"].startswith("RCV-AUD-")


class TestListenerFailureIsolation:
    @pytest.fixture
    def _captured_handlers(self, mocker):
        handlers = {}

        def listens_for(model, _event):
            def decorator(fn):
                handlers.setdefault(model.__name__, []).append(fn)
                return fn

            return decorator

        mocker.patch("sqlalchemy.event.listens_for", side_effect=listens_for)
        return handlers

    def test_savepoint_failure_does_not_propagate(self, _captured_handlers, mocker):
        from types import SimpleNamespace

        from models.events import register_audit_listeners

        failure_hook = mocker.patch("models.events._log_audit_failure")
        register_audit_listeners()

        connection = MagicMock()
        connection.begin_nested.side_effect = RuntimeError("savepoint exploded")
        target = SimpleNamespace(id=9, tenant_id=1, sale_number="S-FAIL", amount_aed=Decimal("1"))

        for handler in _captured_handlers["Sale"]:
            handler(None, connection, target)

        failure_hook.assert_called()

    def test_insert_failure_inside_savepoint_swallowed(self, _captured_handlers, mocker):
        import contextlib
        from types import SimpleNamespace

        from models.events import register_audit_listeners

        mocker.patch("models.events.logger.warning")
        failure_hook = mocker.patch("models.events._log_audit_failure")
        register_audit_listeners()

        connection = MagicMock()
        connection.begin_nested.return_value = contextlib.nullcontext()
        connection.execute.side_effect = RuntimeError("insert exploded")

        targets = {
            "Purchase": SimpleNamespace(
                id=None,
                tenant_id=None,
                purchase_number="P-X",
                amount_aed=Decimal("1"),
            ),
            "Payment": SimpleNamespace(id=None, tenant_id=None, amount_aed=Decimal("1")),
        }
        for name, target in targets.items():
            for handler in _captured_handlers[name]:
                handler(None, connection, target)

        assert failure_hook.call_count == len(_captured_handlers["Purchase"]) + len(_captured_handlers["Payment"])
