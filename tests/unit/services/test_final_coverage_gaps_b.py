"""Final coverage gaps (batch B) — remaining missed statements in six services.

Each test targets a concrete missed statement confirmed by the combined CI
coverage data.  Heavy collaborators are mocked at the service boundary; the
conversion/aggregation math stays real.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ───────────────────────────── services/serial_tracking_service.py ──────────


def _mock_serial_query(mocker, serials):
    q = MagicMock()
    q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = serials
    q.filter.return_value.all.return_value = serials
    mocker.patch("models.product_serial.ProductSerial.query", q)
    return q


class TestSerialTrackingRemaining:
    def test_issue_zero_quantity_returns_empty(self):
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.issue_serials(1, 1, 0, tenant_id=1, reference_type="sale") == []

    def test_issue_serials_sale_links_line(self, mocker):
        serials = [MagicMock(serial_number="SN-1"), MagicMock(serial_number="SN-2")]
        _mock_serial_query(mocker, serials)
        from services.serial_tracking_service import SerialTrackingService

        got = SerialTrackingService.issue_serials(1, 1, 2, tenant_id=1, reference_type="sale", reference_id=42)
        assert got == ["SN-1", "SN-2"]
        assert all(s.status == "sold" for s in serials)
        assert all(s.sale_line_id == 42 for s in serials)

    def test_issue_serials_maintenance_links_line(self, mocker):
        serials = [MagicMock(serial_number="SN-M")]
        _mock_serial_query(mocker, serials)
        from services.serial_tracking_service import SerialTrackingService

        got = SerialTrackingService.issue_serials(1, 1, 1, tenant_id=1, reference_type="maintenance", reference_id=7)
        assert got == ["SN-M"]
        assert serials[0].status == "issued"
        assert serials[0].maintenance_order_line_id == 7

    def test_issue_serials_none_reference_id_stays_unlinked(self, mocker):
        serials = [MagicMock(serial_number="SN-NOREF")]
        _mock_serial_query(mocker, serials)
        from services.serial_tracking_service import SerialTrackingService

        got = SerialTrackingService.issue_serials(1, 1, 1, tenant_id=1, reference_type="sale", reference_id=None)
        assert got == ["SN-NOREF"]
        assert serials[0].status == "sold"

    def test_restore_serials_empty_is_noop(self, mocker):
        q = _mock_serial_query(mocker, [])
        from services.serial_tracking_service import SerialTrackingService

        SerialTrackingService.restore_serials([], tenant_id=1)
        q.filter.assert_not_called()

    def test_restore_serials_resets_issued(self, mocker):
        serials = [MagicMock(), MagicMock()]
        q = _mock_serial_query(mocker, serials)
        from services.serial_tracking_service import SerialTrackingService

        SerialTrackingService.restore_serials(["SN-1", "SN-2"], tenant_id=1)
        q.filter.assert_called_once()
        for serial in serials:
            assert serial.status == "available"
            assert serial.sale_line_id is None
            assert serial.maintenance_order_line_id is None


# ───────────────────────────── services/whatsapp_service.py ────────────────


class TestWhatsAppShipmentStatusRemaining:
    def test_missing_instance_configuration(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_API_KEY", "key")
        monkeypatch.delenv("WHATSAPP_INSTANCE_ID", raising=False)
        from services.whatsapp_service import WhatsAppService

        res = WhatsAppService.send_shipment_status("971501234567", "TRK-1", "in_transit")
        assert res == {"success": False, "error": "Missing configuration"}

    def test_success_builds_message_with_carrier_and_tracking(self, monkeypatch, mocker):
        monkeypatch.setenv("WHATSAPP_API_KEY", "key")
        monkeypatch.setenv("WHATSAPP_INSTANCE_ID", "inst")
        monkeypatch.setenv("WHATSAPP_API_URL", "https://wa.test")
        resp = MagicMock()
        resp.json.return_value = {"id": "msg-1"}
        post = mocker.patch("services.whatsapp_service.requests.post", return_value=resp)
        from services.whatsapp_service import WhatsAppService

        res = WhatsAppService.send_shipment_status("0501234567", "TRK-9", "in_transit", carrier_name="DHL")
        assert res["success"] is True
        assert res["message_id"] == "msg-1"
        assert res["phone"] == "971501234567"
        body = post.call_args.kwargs["data"]["body"]
        assert "DHL" in body and "TRK-9" in body and "في الطريق" in body

    def test_request_exception_returns_error(self, monkeypatch, mocker):
        monkeypatch.setenv("WHATSAPP_API_KEY", "key")
        monkeypatch.setenv("WHATSAPP_INSTANCE_ID", "inst")
        monkeypatch.setenv("WHATSAPP_API_URL", "https://wa.test")
        mocker.patch("services.whatsapp_service.requests.post", side_effect=RuntimeError("offline"))
        from services.whatsapp_service import WhatsAppService

        res = WhatsAppService.send_shipment_status("971501234567", "TRK-1", "delivered")
        assert res["success"] is False
        assert "offline" in res["error"]


# ───────────────────────────── services/shipment_service.py ─────────────────


class TestShipmentRemaining:
    def test_generate_number_without_tenant(self):
        from services.shipment_service import ShipmentService

        assert ShipmentService._generate_shipment_number(None).startswith("SH-")

    @staticmethod
    def _shipment(email=None):
        shipment = MagicMock()
        shipment.recipient_phone = "971501234567"
        shipment.tracking_number = "TRK-1"
        shipment.status = "in_transit"
        shipment.carrier_name = "DHL"
        shipment.tenant_id = 1
        shipment.recipient_email = email
        return shipment

    def test_notify_whatsapp_failure_is_swallowed(self, mocker):
        shipment = self._shipment()
        wa = mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_shipment_status",
            side_effect=RuntimeError("wa down"),
        )
        sms = mocker.patch("services.sms_service.SMSService.is_enabled", return_value=False)
        from services.shipment_service import ShipmentService

        ShipmentService._notify_status(shipment)
        wa.assert_called_once()
        sms.assert_called_once_with(1)

    def test_notify_sms_success(self, mocker):
        shipment = self._shipment()
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_shipment_status",
            return_value={"success": True},
        )
        mocker.patch("services.sms_service.SMSService.is_enabled", return_value=True)
        send = mocker.patch(
            "services.sms_service.SMSService.send_shipment_status",
            return_value={"success": True},
        )
        from services.shipment_service import ShipmentService

        ShipmentService._notify_status(shipment)
        send.assert_called_once()

    def test_notify_sms_failure_is_swallowed(self, mocker):
        shipment = self._shipment()
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_shipment_status",
            return_value={"success": True},
        )
        mocker.patch("services.sms_service.SMSService.is_enabled", return_value=True)
        mocker.patch(
            "services.sms_service.SMSService.send_shipment_status",
            side_effect=RuntimeError("sms down"),
        )
        from services.shipment_service import ShipmentService

        ShipmentService._notify_status(shipment)

    def test_notify_email_failure_is_swallowed(self, mocker):
        shipment = self._shipment(email="ops@example.com")
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_shipment_status",
            return_value={"success": True},
        )
        mocker.patch("services.sms_service.SMSService.is_enabled", return_value=False)
        mocker.patch("flask_mail.Message")
        mocker.patch("extensions.mail.send", side_effect=RuntimeError("smtp down"))
        from services.shipment_service import ShipmentService

        ShipmentService._notify_status(shipment)

    def test_notify_outer_failure_is_swallowed(self):
        class Exploding:
            def __getattr__(self, _name):
                raise RuntimeError("boom")

        from services.shipment_service import ShipmentService

        ShipmentService._notify_status(Exploding())


# ───────────────────────── services/customer_statement_service.py ──────────


class TestCustomerStatementRemaining:
    def test_to_base_amount_rate_arcs(self):
        from services.customer_statement_service import _to_base_amount

        # Unparseable rate -> fallback to 1 (lines 38-42, 44).
        assert _to_base_amount(Decimal("10"), "USD", "not-a-rate", "AED") == Decimal("10.000")
        # Non-positive rate -> forced to 1 (line 43).
        assert _to_base_amount(Decimal("10"), "USD", "0", "AED") == Decimal("10.000")

    def test_opening_balance_allocations_refunds_and_maintenance_receipt(
        self, db_session, sample_customer, sample_tenant, sample_user
    ):
        from models import Payment, Receipt
        from models.maintenance import MaintenanceOrder, MaintenanceReceipt
        from services.customer_statement_service import CustomerStatementService

        past = datetime(2020, 1, 1, 10, 0, 0)

        allocated_payment = Payment(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            payment_number="PAY-GAP-ALLOC",
            payment_type="sale_payment",
            reference_number="RCP-GAP-ALLOC",
            direction="incoming",
            amount=Decimal("9"),
            amount_aed=Decimal("9"),
            payment_method="cash",
            payment_confirmed=True,
            payment_date=past,
        )
        pending_receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number="RCP-GAP-PENDING",
            customer_id=sample_customer.id,
            amount=Decimal("3"),
            amount_aed=Decimal("3"),
            payment_method="cash",
            payment_confirmed=False,
            receipt_date=past,
        )
        confirmed_receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number="RCP-GAP-CONFIRMED",
            customer_id=sample_customer.id,
            amount=Decimal("5"),
            amount_aed=Decimal("5"),
            payment_method="cash",
            payment_confirmed=True,
            receipt_date=past,
        )
        order = MaintenanceOrder(
            tenant_id=sample_tenant.id,
            order_number="MO-GAP-OPEN",
            customer_id=sample_customer.id,
            received_by=sample_user.id,
            order_date=past,
            currency="AED",
            base_currency="AED",
        )
        db_session.add(order)
        db_session.flush()
        maintenance_receipt = MaintenanceReceipt(
            tenant_id=sample_tenant.id,
            order_id=order.id,
            receipt_number="MRC-GAP-OPEN",
            receipt_date=past,
            amount=Decimal("7"),
            payment_mode="cash",
            cashier_id=sample_user.id,
            is_refund=True,
        )
        db_session.add_all([allocated_payment, pending_receipt, confirmed_receipt, maintenance_receipt])
        db_session.flush()

        ctx = CustomerStatementService.build_statement_context(
            record_id=sample_customer.id,
            date_from="2099-01-01",
            date_to=None,
            transaction_type="all",
            default_currency="AED",
            tenant_id=sample_tenant.id,
            branch_id=None,
        )
        assert ctx["transactions"][0]["type"] == "opening"

    def test_sale_payments_equal_dates_exercise_last_payment_branch(
        self, db_session, sample_customer, sample_tenant, sample_user, sample_warehouse
    ):
        from models import Payment, Sale
        from services.customer_statement_service import CustomerStatementService

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="S-GAP-PAYS",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            warehouse_id=sample_warehouse.id,
            sale_date=datetime(2026, 1, 1, 9, 0, 0),
            status="confirmed",
            subtotal=Decimal("20"),
            total_amount=Decimal("20"),
            amount=Decimal("20"),
            amount_aed=Decimal("20"),
            payment_status="unpaid",
        )
        db_session.add(sale)
        db_session.flush()
        same_day = datetime(2026, 1, 2, 12, 0, 0)
        for number in ("PAY-GAP-EQ-1", "PAY-GAP-EQ-2"):
            db_session.add(
                Payment(
                    tenant_id=sample_tenant.id,
                    customer_id=sample_customer.id,
                    sale_id=sale.id,
                    payment_number=number,
                    payment_type="sale_payment",
                    direction="incoming",
                    amount=Decimal("10"),
                    amount_aed=Decimal("10"),
                    payment_method="cash",
                    payment_confirmed=True,
                    payment_date=same_day,
                )
            )
        db_session.flush()

        ctx = CustomerStatementService.build_statement_context(
            record_id=sample_customer.id,
            date_from=None,
            date_to=None,
            transaction_type="all",
            default_currency="AED",
            tenant_id=sample_tenant.id,
            branch_id=None,
        )
        sale_t = next(t for t in ctx["transactions"] if t["type"] == "sale")
        last_date = sale_t["sale"]["last_payment_date"]
        assert (last_date.replace(tzinfo=None) if last_date else last_date) == same_day
        assert len(sale_t["sale"]["payments"]) == 2


# ───────────────────────────── services/sale_service.py ─────────────────────


class TestSaleServiceRemaining:
    def test_recompute_commission_basis_vat_inclusive(self):
        from services.sale_service import SaleService

        entry = MagicMock(cost_basis=Decimal("10"), percentage=Decimal("10"), currency="AED", tenant_id=1)
        sale = MagicMock(tax_rate=Decimal("18"), prices_include_vat=True, exchange_rate=Decimal("1"))
        line = MagicMock(line_total=Decimal("118"), tax_category="standard")
        with (
            patch.object(SaleService, "_commission_margin", return_value=Decimal("5")) as margin,
            patch.object(SaleService, "_commission_base_aed", return_value=Decimal("5")),
        ):
            SaleService.recompute_commission_basis(entry, sale, line)
        assert margin.call_args.args[0] == Decimal("100.000")

    def test_invoice_discount_clamps_negative_base_and_margin(self):
        from services.sale_service import SaleService

        entry = MagicMock()
        context = [(entry, Decimal("100"), Decimal("10"), Decimal("10"), Decimal("5"))]
        with patch.object(SaleService, "_commission_base_aed", return_value=Decimal("50")):
            SaleService._apply_invoice_discount_to_commissions(
                context,
                Decimal("100"),
                Decimal("100"),
                Decimal("1"),
                prices_include_vat=True,
                tax_rate=Decimal("18"),
            )
        assert entry.base_amount_aed == Decimal("0.000")
        assert entry.profit_margin == Decimal("0.000")

    @pytest.fixture
    def split_mocks(self):
        from services.sale_service import SaleService

        with (
            patch.object(SaleService, "create_payment_for_sale") as create_payment,
            patch("services.sale_service.db") as mock_db,
            patch("models.Payment") as payment_cls,
            patch("services.sale_service.GLService"),
            patch("services.sale_service.post_or_fail"),
            patch(
                "services.document_sequence_service.DocumentSequenceService.next_number",
                return_value="PRE-GAP",
            ),
        ):
            payment_cls.return_value = MagicMock(id=99)
            yield MagicMock(create_payment=create_payment, db=mock_db, payment_cls=payment_cls)

    def test_cash_excess_records_change_note(self, split_mocks):
        from services.sale_service import SaleService

        sale = MagicMock(amount_aed=Decimal("50"), notes="")
        prepared = [
            {
                "amount": Decimal("70"),
                "amount_aed": Decimal("70"),
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": Decimal("1"),
            }
        ]
        SaleService._create_split_payments(sale, prepared)
        assert "[باقي نقدي]" in sale.notes
        split_mocks.db.session.add.assert_not_called()

    def test_book_overpayment_cash_change_returns_early(self, split_mocks):
        from services.sale_service import SaleService

        sale = MagicMock(notes="")
        chunk = {"payment_method": "cash", "currency": "AED", "exchange_rate": Decimal("1")}
        SaleService._book_overpayment_prepayment(sale, Decimal("20"), chunk)
        assert "[باقي نقدي]" in sale.notes
        split_mocks.db.session.add.assert_not_called()

    def test_book_overpayment_non_cash_creates_prepayment(self, split_mocks):
        from services.sale_service import SaleService

        customer = MagicMock()
        sale = MagicMock(
            tenant_id=1,
            branch_id=2,
            customer_id=3,
            seller_id=4,
            sale_number="S-GAP",
            notes="",
            customer=customer,
        )
        chunk = {"payment_method": "card", "currency": "AED", "exchange_rate": Decimal("1")}
        SaleService._book_overpayment_prepayment(sale, Decimal("20"), chunk)
        assert "[دفع زائد]" in sale.notes
        split_mocks.db.session.add.assert_called_once()
        split_mocks.db.session.flush.assert_called_once()
        customer.apply_receipt.assert_called_once_with(Decimal("20"))
        assert split_mocks.payment_cls.call_args.kwargs["payment_number"] == "PRE-GAP"


# ─────────────────────────── services/backup_scoped_engine.py ───────────────


def _write_scope_data(tmp_path, tables):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    meta = {"table_order": list(tables.keys())}
    for table, rows in tables.items():
        (data_dir / f"{table}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )
    (data_dir / "schema_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _mock_restore_engine(mocker, table_exists=True, insert_raises=None, column_names=None):
    conn = mocker.MagicMock()
    txn = mocker.MagicMock()
    txn.__enter__.return_value = conn
    txn.__exit__.return_value = None
    conn.begin.return_value = txn
    seq_counter = {"n": 500}
    cols = column_names or ["id", "tenant_id", "branch_id"]

    def scalar_side():
        seq_counter["n"] += 1
        return seq_counter["n"]

    result = mocker.MagicMock()
    result.scalar.side_effect = scalar_side
    col_result = mocker.MagicMock()
    col_result.__iter__.return_value = iter((c,) for c in cols)

    def execute_side(sql, params=None):
        sql_s = str(sql)
        if "information_schema.columns" in sql_s:
            return col_result
        if insert_raises and "INSERT INTO" in sql_s:
            raise insert_raises
        return result

    conn.execute.side_effect = execute_side
    engine = mocker.MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = None
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = None
    mocker.patch("sqlalchemy.create_engine", return_value=engine)
    mocker.patch("services.backup_scoped_engine.table_exists", return_value=table_exists)
    return conn


class TestBackupScopedEngineRemaining:
    def test_dry_run_simulates_and_rolls_back(self, mocker, tmp_path):
        from services.backup_scope_config import SCOPE_TENANT
        from services.backup_scoped_engine import restore_scoped_to_target

        tables = {
            "tenants": [{"id": 1, "slug": "acme"}],
            "customers": [{"id": 10, "tenant_id": 1}],
            "empty_table": [],
        }
        _write_scope_data(tmp_path, tables)
        mocker.patch("services.backup_service.BackupService._urls_same_database", return_value=False)
        mocker.patch("services.backup_scoped_engine.ensure_target_schema", return_value=(True, ""))
        _mock_restore_engine(mocker)

        result = restore_scoped_to_target(
            str(tmp_path),
            {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
            "postgres://target",
            confirmation="RESTORE CONFIRM",
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["target_tenant_id"] == 1

    def test_ensure_schema_falls_through_when_pg_tool_missing(self, mocker):
        from services.backup_scoped_engine import ensure_target_schema

        mocker.patch.dict(os.environ, {"DATABASE_URL": "postgres://src/db"}, clear=False)
        mocker.patch("services.backup_service.BackupService._urls_same_database", return_value=False)
        mocker.patch(
            "services.backup_service.BackupService._parse_db_url",
            return_value={"host": "h", "port": "5432", "username": "u", "password": "", "dbname": "d"},
        )
        mocker.patch("services.backup_service.BackupService._resolve_pg_tool", return_value=None)
        mocker.patch(
            "services.backup_exec.run_python_module",
            return_value=MagicMock(returncode=0, stderr="", stdout=""),
        )
        mocker.patch("app.create_app", side_effect=RuntimeError("skip app init"))

        ok, err = ensure_target_schema("postgres://tgt/db")
        assert ok is True
        assert err == ""

    def test_ensure_schema_falls_through_when_dump_fails(self, mocker):
        from services.backup_scoped_engine import ensure_target_schema

        mocker.patch.dict(os.environ, {"DATABASE_URL": "postgres://src/db"}, clear=False)
        mocker.patch("services.backup_service.BackupService._urls_same_database", return_value=False)
        mocker.patch(
            "services.backup_service.BackupService._parse_db_url",
            return_value={"host": "h", "port": "5432", "username": "u", "password": "", "dbname": "d"},
        )
        mocker.patch(
            "services.backup_service.BackupService._resolve_pg_tool",
            side_effect=lambda tool, _env: tool,
        )
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=MagicMock(returncode=1, stderr="", stdout=""),
        )
        mocker.patch(
            "services.backup_exec.run_python_module",
            return_value=MagicMock(returncode=0, stderr="", stdout=""),
        )
        mocker.patch("app.create_app", side_effect=RuntimeError("skip app init"))

        ok, _err = ensure_target_schema("postgres://tgt/db")
        assert ok is True

    def test_ensure_schema_without_source_url_uses_flask_upgrade(self, mocker):
        from services.backup_scoped_engine import ensure_target_schema

        mocker.patch.dict(os.environ, {}, clear=True)
        mocker.patch(
            "services.backup_exec.run_python_module",
            return_value=MagicMock(returncode=0, stderr="", stdout=""),
        )
        app_obj = MagicMock()
        app_obj.app_context.return_value.__enter__ = MagicMock(return_value=None)
        app_obj.app_context.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch("app.create_app", return_value=app_obj)
        mocker.patch("utils.system_init._ensure_core_data")

        ok, _err = ensure_target_schema("postgres://tgt/db")
        assert ok is True
