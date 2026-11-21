"""Coverage-gap tests for two model modules.

The statements left uncovered in ``models/maintenance.py`` and
``models/product_import_job.py`` are mostly ``__repr__`` methods and small
calculation helpers.  They need no database: transient instances are enough,
and the two properties that walk relationships use patched class attributes so
the tests stay at the model layer (no HTTP concepts, no production changes).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest

from models.maintenance import (
    MaintenanceDeviceRegistry,
    MaintenanceDiscountMode,
    MaintenanceInvoice,
    MaintenanceOrder,
    MaintenanceOrderLine,
    MaintenanceOrderService,
    MaintenanceOrderStatusLog,
    MaintenanceOrderWarrantyStatus,
    MaintenancePurchaseOrder,
    MaintenancePurchaseOrderLine,
    MaintenanceReceipt,
    MaintenanceReturn,
    MaintenanceReturnLine,
    MaintenanceServiceTemplate,
    MaintenanceSetting,
    MaintenanceWarrantyAudit,
)
from models.product_import_job import (
    ProductImportJob,
    ProductImportJobStatus,
    ProductImportRollbackLog,
    ProductImportTemplate,
)


class TestMaintenanceOrderProperties:
    def test_repr_and_conversion_flag(self):
        order = MaintenanceOrder(order_number="MN-1", status="received")
        assert "MN-1" in repr(order)
        assert "received" in repr(order)
        assert order.can_be_converted_to_closed is False
        order.status = "ready"
        assert order.can_be_converted_to_closed is True

    def test_total_cost_aed(self):
        priced = SimpleNamespace(movement=object(), is_archived=False, cost_aed=Decimal("10.000"))
        archived = SimpleNamespace(movement=object(), is_archived=True, cost_aed=Decimal("88.000"))
        no_movement = SimpleNamespace(movement=None, is_archived=False, cost_aed=Decimal("99.000"))
        order = MaintenanceOrder()
        with patch.object(
            MaintenanceOrder,
            "lines",
            new_callable=PropertyMock,
            return_value=[priced, archived, no_movement],
        ):
            assert order.total_cost_aed == Decimal("10.000")

    def test_net_profit_estimate_without_invoice(self):
        order = MaintenanceOrder()
        with patch.object(MaintenanceOrder, "invoice", new_callable=PropertyMock, return_value=None):
            assert order.net_profit_estimate is None

    def test_net_profit_estimate_unposted_invoice(self):
        order = MaintenanceOrder()
        unposted = SimpleNamespace(posted=False)
        with patch.object(MaintenanceOrder, "invoice", new_callable=PropertyMock, return_value=unposted):
            assert order.net_profit_estimate is None

    def test_net_profit_estimate_posted_invoice(self):
        order = MaintenanceOrder(
            total_amount=Decimal("118.000"),
            tax_amount=Decimal("18.000"),
            currency="AED",
            exchange_rate=Decimal("1"),
            base_currency="AED",
        )
        posted = SimpleNamespace(posted=True)
        with (
            patch.object(MaintenanceOrder, "invoice", new_callable=PropertyMock, return_value=posted),
            patch.object(
                MaintenanceOrder,
                "total_cost_aed",
                new_callable=PropertyMock,
                return_value=Decimal("20.000"),
            ),
        ):
            assert order.net_profit_estimate == Decimal("80.000")

    def test_to_dict(self):
        order = MaintenanceOrder(
            order_number="MN-2",
            status="ready",
            total_amount=Decimal("100.000"),
            paid_amount=Decimal("40.000"),
            balance_due=Decimal("60.000"),
            currency="AED",
            amount_aed=Decimal("100.000"),
        )
        data = order.to_dict()
        assert data["order_number"] == "MN-2"
        assert data["status"] == "ready"
        assert data["total_amount"] == 100.0
        assert data["balance_due"] == 60.0
        assert data["closed_at"] is None
        assert data["created_at"] is None


class TestMaintenanceOrderLineProperties:
    def test_repr(self):
        line = MaintenanceOrderLine(product_id=7, quantity=Decimal("2.000"))
        assert "7" in repr(line)
        assert "2.000" in repr(line)

    def test_net_line_total_percent_discount(self):
        line = MaintenanceOrderLine(
            quantity=Decimal("2"),
            quantity_returned=Decimal("0"),
            unit_price=Decimal("100"),
            discount_percent=Decimal("10"),
            discount_mode=MaintenanceDiscountMode.PERCENT,
        )
        assert line.net_line_total == Decimal("180")

    def test_net_line_total_value_discount(self):
        line = MaintenanceOrderLine(
            quantity=Decimal("2"),
            quantity_returned=Decimal("1"),
            unit_price=Decimal("100"),
            discount_value=Decimal("5"),
            discount_mode=MaintenanceDiscountMode.VALUE,
        )
        assert line.net_line_total == Decimal("95")


class TestMaintenanceReprs:
    def test_document_and_child_reprs(self):
        assert "SVC-1" in repr(MaintenanceOrderService(service_code="SVC-1"))
        log = MaintenanceOrderStatusLog(order_id=1, from_status=None, to_status="received")
        assert "received" in repr(log)
        assert "R-1" in repr(MaintenanceReceipt(receipt_number="R-1", amount=Decimal("10")))
        assert "MINV-1" in repr(MaintenanceInvoice(invoice_number="MINV-1", total_amount=Decimal("10")))
        assert "RET-1" in repr(MaintenanceReturn(return_number="RET-1", total_value=Decimal("10")))
        assert "qty=" in repr(MaintenanceReturnLine(quantity=Decimal("1")))

    def test_setting_template_registry_audit_reprs(self):
        assert "tenant_id=1" in repr(MaintenanceSetting(tenant_id=1))
        assert "SRV-1" in repr(MaintenanceServiceTemplate(service_code="SRV-1", name="Oil change"))
        assert "SN-1" in repr(MaintenanceDeviceRegistry(serial_number="SN-1"))
        assert "checked" in repr(MaintenanceWarrantyAudit(action="checked"))

    def test_purchase_order_reprs(self):
        order = MaintenancePurchaseOrder(po_number="PO-1", status="draft", total_amount=Decimal("10"))
        assert "PO-1" in repr(order)
        line = MaintenancePurchaseOrderLine(product_id=9, quantity=Decimal("3"))
        assert "9" in repr(line)


class TestMaintenanceDeviceRegistryWarranty:
    def test_naive_start_date_is_treated_as_utc(self):
        device = MaintenanceDeviceRegistry(
            is_active=True,
            is_under_warranty=True,
            warranty_start_date=(datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None),
            warranty_end_date=datetime.now(UTC) + timedelta(days=1),
        )
        assert device.warranty_status == MaintenanceOrderWarrantyStatus.UNDER_WARRANTY


class TestProductImportJob:
    def _job(self, **kwargs):
        defaults = dict(
            id=1,
            tenant_id=1,
            job_name="import",
            status=ProductImportJobStatus.COMPLETED,
            created_product_ids=[1, 2],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            total_rows=10,
            processed_rows=5,
            errors=[],
            warnings=[],
            summary={"ok": 1},
        )
        defaults.update(kwargs)
        return ProductImportJob(**defaults)

    def test_repr(self):
        job = self._job()
        assert "ProductImportJob" in repr(job)
        assert "completed" in repr(job)
        assert "tenant=1" in repr(job)

    def test_progress_percent_zero_rows(self):
        job = self._job(total_rows=0, processed_rows=0)
        assert job.progress_percent == 0.0

    def test_progress_percent_normal_and_capped(self):
        assert self._job(total_rows=10, processed_rows=5).progress_percent == 50.0
        assert self._job(total_rows=10, processed_rows=20).progress_percent == 100.0

    def test_duration_seconds_started_only(self):
        job = self._job(started_at=datetime.now(UTC) - timedelta(seconds=30), completed_at=None)
        duration = job.duration_seconds
        assert duration is not None
        assert 29 <= duration <= 32

    def test_to_dict_without_details(self):
        job = self._job(errors=[{"row": 1, "error": "x"}], warnings=[{"row": 2}])
        data = job.to_dict()
        assert "errors" not in data
        assert "warnings" not in data
        assert data["status"] == "completed"
        assert data["progress_percent"] == 50.0
        assert data["can_rollback"] == [1, 2]
        assert data["started_at"] is None
        assert data["created_at"] == "2026-01-01T00:00:00+00:00"

    def test_to_dict_with_details_limits_lists(self):
        job = self._job(
            errors=[{"row": i} for i in range(60)],
            warnings=[{"row": i} for i in range(60)],
        )
        data = job.to_dict(include_details=True)
        assert len(data["errors"]) == 50
        assert len(data["warnings"]) == 50
        assert data["summary"] == {"ok": 1}


class TestProductImportTemplate:
    def _template(self, **kwargs):
        defaults = dict(
            id=1,
            tenant_id=1,
            name="Default",
            column_mapping={"Name": "name", "price ": "price"},
            default_values={"category": "general"},
            required_fields=["name", "price"],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        defaults.update(kwargs)
        return ProductImportTemplate(**defaults)

    def test_repr(self):
        template = self._template()
        assert "Default" in repr(template)
        assert "tenant=1" in repr(template)

    def test_to_dict(self):
        data = self._template().to_dict()
        assert data["name"] == "Default"
        assert data["column_mapping"] == {"Name": "name", "price ": "price"}
        assert data["created_at"] == "2026-01-01T00:00:00+00:00"

    def test_to_dict_list(self):
        templates = [self._template(name="A"), self._template(name="B")]
        assert [item["name"] for item in ProductImportTemplate.to_dict_list(templates)] == ["A", "B"]

    def test_apply_to_dataframe(self):
        pd = pytest.importorskip("pandas")
        frame = pd.DataFrame({" Name ": ["Widget"], "Price ": [10], "Ignored": [99]})
        result = self._template().apply_to_dataframe(frame, tenant_id=1)
        assert list(result.columns) == ["name", "price", "category"]
        assert result.loc[0, "name"] == "Widget"

    def test_apply_to_dataframe_skips_defaults_for_existing_columns(self):
        pd = pytest.importorskip("pandas")
        frame = pd.DataFrame({"name": ["Widget"]})
        template = self._template(
            column_mapping={"name": "name"},
            default_values={"name": "fallback", "category": "general"},
            required_fields=["name"],
        )
        result = template.apply_to_dataframe(frame, tenant_id=1)
        assert list(result.columns) == ["name", "category"]
        assert result.loc[0, "name"] == "Widget"

    def test_apply_to_dataframe_missing_required(self):
        pd = pytest.importorskip("pandas")
        frame = pd.DataFrame({" Name ": ["Widget"]})
        template = self._template(required_fields=["price"])
        with pytest.raises(ValueError, match="Missing required fields"):
            template.apply_to_dataframe(frame, tenant_id=1)


class TestProductImportRollbackLog:
    def test_created_at_default_is_callable(self):
        default = ProductImportRollbackLog.__table__.c.created_at.default
        assert default is not None
        assert default.arg(None).tzinfo is not None

    def test_transient_instantiation(self):
        log = ProductImportRollbackLog(original_job_id=1, rollback_job_id=2)
        assert log.original_job_id == 1
        assert log.rollback_job_id == 2
