"""Coverage boost for services/print_service.py.

Targets: resolve_template branches, _get_model, _get_tenant_context tid-None,
render_pdf static-folder fallback, _json_safe, create_snapshot branches,
audit_print user fallback, bulk single page, get_document guards, shipment /
history / recent-history fetches. Real service calls throughout.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestResolveTemplate:
    def test_sale_requested_valid_and_invalid(self, db_session, sample_tenant):
        from services.print_service import PrintService

        assert PrintService.resolve_template("sale", sample_tenant.id, "classic") == "invoices/classic.html"
        got = PrintService.resolve_template("sale", sample_tenant.id, "nope")
        assert got.startswith("invoices/")

    def test_receipt_payment_requested(self):
        from services.print_service import PrintService

        assert PrintService.resolve_template("receipt", None, "minimal") == "receipts/minimal.html"
        assert PrintService.resolve_template("payment", None, "nope").startswith("receipts/")

    def test_static_entry_and_unknown_fallback(self):
        from services.print_service import PrintService

        assert PrintService.resolve_template("expense", None, None) == "expenses/print.html"
        assert PrintService.resolve_template("mystery-doc", None, None) == "invoices/modern.html"

    def test_no_tenant_uses_modern(self):
        from services.print_service import PrintService

        assert PrintService.resolve_template("sale", None, None) == "invoices/modern.html"


class TestModelAndTenantContext:
    def test_get_model_returns_class(self):
        import models
        from services.print_service import PrintService

        assert PrintService._get_model("Customer") is models.Customer

    def test_tenant_context_with_none_tid(self, app, db_session, sample_tenant, mocker):
        from services.print_service import PrintService

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id)
        with app.app_context():
            ctx = PrintService._get_tenant_context(None)
        assert ctx["print_tenant_id"] == sample_tenant.id
        assert "company" in ctx


class TestJsonSafe:
    def test_conversions(self):
        from services.print_service import PrintService

        out = PrintService._json_safe(
            {
                "d": Decimal("1.5"),
                "dt": datetime(2026, 1, 2, 3, 4, 5),
                "day": date(2026, 1, 3),
                "lst": [Decimal("2"), (Decimal("3"),)],
                "n": 7,
                "s": "x",
            }
        )
        assert out["d"] == 1.5
        assert out["dt"].startswith("2026-01-02")
        assert out["day"] == "2026-01-03"
        assert out["lst"][0] == 2.0 and out["lst"][1] == [3.0]


class TestRenderPdfFallback:
    def test_static_folder_missing_falls_back_to_html(self, app, mocker):
        from services.print_service import PrintService

        mocker.patch("services.print_service.PrintService.render_print", return_value="<html>hi</html>")
        from unittest.mock import MagicMock

        fake_app = MagicMock(static_folder=None)
        fake_app.logger.error = MagicMock()
        mocker.patch("services.print_service.current_app", fake_app)
        import sys

        fake_wp = MagicMock()
        fake_wp.HTML.return_value.write_pdf.side_effect = RuntimeError("boom")
        mocker.patch.dict(sys.modules, {"weasyprint": fake_wp})
        result = PrintService.render_pdf("t.html")
        assert result == b"<html>hi</html>"


class TestCreateSnapshot:
    def test_unknown_registry_skipped(self, app, db_session, sample_tenant):
        from services.print_service import PrintService

        with app.app_context():
            assert PrintService.create_snapshot(sample_tenant.id, "nope", 1) is None

    def test_document_not_found_skipped(self, app, db_session, sample_tenant):
        from services.print_service import PrintService

        with app.app_context():
            assert PrintService.create_snapshot(sample_tenant.id, "payment", 99999999) is None

    def test_snapshot_with_passed_document(self, app, db_session, sample_tenant, sample_customer):
        from services.print_service import PrintService

        with app.app_context():
            PrintService.create_snapshot(
                None, "customer_statement", sample_customer.id, reason="print", document=sample_customer
            )
            db_session.flush()
            from models.document_snapshot import DocumentSnapshot

            snap = DocumentSnapshot.query.filter_by(document_id=sample_customer.id).first()
            assert snap is not None
            assert snap.tenant_id == sample_tenant.id

    def test_snapshot_serialize_fallback_columns(self, app, db_session, sample_tenant, sample_customer, mocker):
        from services.print_service import PrintService

        mocker.patch.object(
            type(sample_customer), "to_dict", new_callable=mocker.PropertyMock, side_effect=RuntimeError("no dict")
        )
        with app.app_context():
            PrintService.create_snapshot(
                sample_tenant.id, "customer_statement", sample_customer.id, reason="finalize", document=sample_customer
            )
            db_session.flush()

    def test_snapshot_outer_exception_non_blocking(self, app, db_session, sample_tenant, mocker):
        from services.print_service import PrintService

        mocker.patch("services.print_service.PrintService._get_model", side_effect=RuntimeError("model boom"))
        with app.app_context():
            assert PrintService.create_snapshot(sample_tenant.id, "payment", 1) is None


class TestAuditBulkFetches:
    def test_audit_falls_back_to_user_context(self, app, db_session, sample_tenant, mocker):
        from services.print_service import PrintService

        mocker.patch(
            "services.print_service.PrintService._user_context",
            return_value={"print_user_id": 42, "print_user_name": "u"},
        )
        with app.app_context():
            PrintService.audit_print(sample_tenant.id, "sale", 7)
            db_session.flush()
            from models.print_history import PrintHistory

            row = PrintHistory.query.filter_by(document_id=7).first()
            assert row is not None
            assert row.user_id == 42

    def test_bulk_single_page_no_break(self, app, mocker):
        from services.print_service import PrintService

        mocker.patch("services.print_service.PrintService.render_print", return_value="<p>one</p>")
        with app.app_context():
            html = PrintService.bulk_print_documents(
                [{"type": "sale", "context": {"a": 1}}], {"sale": "s.html"}, tenant_id=1
            )
        assert "<p>one</p>" in html
        assert '<div class="page-break">' not in html

    def test_bulk_missing_template_skipped(self, app, mocker):
        from services.print_service import PrintService

        render = mocker.patch("services.print_service.PrintService.render_print", return_value="<p/>")
        with app.app_context():
            html = PrintService.bulk_print_documents([{"type": "sale"}], {"other": "x.html"}, tenant_id=1)
        render.assert_not_called()
        assert "لا توجد مستندات" in html

    def test_get_document_guard_and_fetch(self, db_session, sample_customer, sample_tenant):
        import pytest as _pt

        from models import Customer
        from services.print_service import PrintService

        with _pt.raises(ValueError):
            PrintService.get_document(Customer, 1, None)
        found = PrintService.get_document(Customer, sample_customer.id, sample_tenant.id)
        assert found.id == sample_customer.id
        assert PrintService.get_tenant_document(Customer, sample_customer.id, sample_tenant.id) is not None

    def test_shipment_history_recent(self, db_session, sample_tenant, sample_customer, sample_user, sample_branch):
        from datetime import UTC
        from datetime import datetime as _dt

        from models import Sale, Shipment
        from services.print_service import PrintService

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=_uniq("SAL"),
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=_dt.now(UTC),
            status="confirmed",
            subtotal=Decimal("10"),
            total_amount=Decimal("10"),
            amount=Decimal("10"),
            amount_aed=Decimal("10"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        ship = Shipment(
            tenant_id=sample_tenant.id,
            source_type="sale",
            source_id=sale.id,
            sale_id=sale.id,
            status="pending",
        )
        db_session.add(ship)
        db_session.flush()
        db_session.commit()
        assert PrintService.get_shipment_for_sale(sale.id, sample_tenant.id) is not None
        assert PrintService.get_shipment_for_sale(99999999, sample_tenant.id) is None
        PrintService.audit_print(sample_tenant.id, "sale", sale.id, user_id=sample_user.id)
        db_session.flush()
        q = PrintService.history_query(sample_tenant.id)
        assert q.count() >= 1
        recent = PrintService.list_recent_history(sample_tenant.id, limit=5)
        assert len(recent) >= 1
