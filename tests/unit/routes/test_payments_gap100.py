"""Gap100 for routes/payments.py line 1175 and surrounding restore_receipt branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def payments_gap_client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    app = app_factory(payments_bp, public_bp)
    return app.test_client()


class TestRestoreReceiptGap100:
    """Line 1175 abort 404 and 1176-1177 branch scope 403."""

    def test_restore_receipt_archived_none_404(self, payments_gap_client):
        with (
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("routes.payments.PaymentService.find_archived_record", return_value=None),
        ):
            resp = payments_gap_client.post("/payments/receipts/999999/restore")
        assert resp.status_code == 404

    def test_restore_receipt_branch_mismatch_403(self, payments_gap_client):
        archived = MagicMock()
        archived.data = {"branch_id": 9}
        with (
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("routes.payments.PaymentService.find_archived_record", return_value=archived),
            patch("utils.decorators.branch_scope_id", return_value=2),
            patch("routes.payments.render_template", return_value="forbidden"),
        ):
            resp = payments_gap_client.post("/payments/receipts/1/restore")
        assert resp.status_code == 403

    def test_restore_receipt_success_redirects(self, payments_gap_client):
        archived = MagicMock()
        archived.data = {"branch_id": None}
        ctx = MagicMock()
        ctx.__enter__.return_value = ctx
        ctx.__exit__.return_value = False
        with (
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("routes.payments.PaymentService.find_archived_record", return_value=archived),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.atomic_transaction", return_value=ctx),
            patch("routes.payments.db.session.delete"),
            patch("routes.payments.LoggingCore.log_audit"),
        ):
            resp = payments_gap_client.post("/payments/receipts/1/restore", follow_redirects=False)
        assert resp.status_code == 302
        assert "/payments/archived" in resp.location or "/payments/receipts" in resp.location or resp.location.endswith("/archived")

    def test_restore_receipt_exception_still_redirects(self, payments_gap_client):
        archived = MagicMock()
        archived.data = {}
        ctx = MagicMock()
        ctx.__enter__.return_value = ctx
        ctx.__exit__.return_value = False
        # simulate exception during atomic_transaction block
        with (
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("routes.payments.PaymentService.find_archived_record", return_value=archived),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.atomic_transaction", return_value=ctx),
            patch("routes.payments.db.session.delete", side_effect=RuntimeError("db down")),
            patch("routes.payments.current_app.logger"),
        ):
            resp = payments_gap_client.post("/payments/receipts/1/restore", follow_redirects=False)
        assert resp.status_code == 302
