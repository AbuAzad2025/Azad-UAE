"""Regression tests for maintenance calculations and fail-closed financial paths."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from models import MaintenanceDeviceRegistry, MaintenanceOrderWarrantyStatus, MaintenanceWarrantyAudit
from services.maintenance_gl_service import MaintenanceGLService
from services.maintenance_order_service import MaintenanceService, _validate_line_values
from services.maintenance_stock_service import MaintenanceStockService
from services.maintenance_warranty_service import WarrantyService


def _without_document(function: Any, *args: Any) -> Any:
    """Call a financial function with no document behind it.

    The typed signatures say a posting needs a document, so the call is
    deliberately outside the contract - the guard is what has to hold when
    a caller ignores it.
    """
    return function(*args)


@pytest.mark.parametrize(
    "qty,price,percent,value,mode,tax",
    [
        ("-1", "10", "0", "0", "percent", "5"),
        ("1", "-10", "0", "0", "percent", "5"),
        ("1", "10", "101", "0", "percent", "5"),
        ("1", "10", "0", "11", "value", "5"),
        ("1", "10", "0", "0", "invalid", "5"),
        ("1", "10", "0", "0", "percent", "101"),
        ("1", "10", "1", "1", "percent", "5"),
        ("NaN", "10", "0", "0", "percent", "5"),
        ("1.0001", "10", "0", "0", "percent", "5"),
        ("1000000", "1000000", "0", "0", "percent", "5"),
    ],
)
def test_invalid_financial_inputs_are_rejected(app, qty, price, percent, value, mode, tax):
    with pytest.raises(ValueError):
        _validate_line_values(qty, price, percent, value, mode, tax)


def _line(*, quantity=None, price="0", mode="percent", percent="0", value="0", tax="5"):
    data = dict(
        is_archived=False,
        unit_price=Decimal(price),
        discount_percent=Decimal(percent),
        discount_value=Decimal(value),
        discount_mode=mode,
        tax_rate=Decimal(tax),
    )
    if quantity is not None:
        data["quantity"] = Decimal(quantity)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    "inclusive,expected_taxable,expected_tax,expected_total",
    [
        (False, "256.500", "12.825", "269.325"),
        (True, "244.286", "12.214", "256.500"),
    ],
)
def test_line_and_order_discounts_and_vat_are_applied_once(
    app, inclusive, expected_taxable, expected_tax, expected_total
):
    part = _line(quantity="2", price="100", mode="value", value="10")
    service = _line(price="105")
    order = SimpleNamespace(
        lines=[part],
        services_lines=[service],
        discount_total_percent=Decimal("0"),
        discount_total_value=Decimal("28.500"),
        prices_include_vat=inclusive,
        paid_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        currency="AED",
        base_currency="AED",
        exchange_rate=Decimal("1"),
    )

    MaintenanceService._recalculate_order_totals(order)

    assert part.line_total == Decimal("180.000")
    assert order.discount_line_total == Decimal("20.000")
    assert order.subtotal == Decimal("285.000")
    assert order.taxable_amount == Decimal(expected_taxable)
    assert order.tax_amount == Decimal(expected_tax)
    assert order.total_amount == Decimal(expected_total)
    assert order.balance_due == order.total_amount
    assert order.amount_aed == order.total_amount


def test_report_sums_base_currency_and_excludes_tax_from_revenue(mocker):
    invoices = [
        SimpleNamespace(
            currency="USD",
            exchange_rate=Decimal("2"),
            total_amount=Decimal("110"),
            tax_amount=Decimal("10"),
            paid_amount=Decimal("100"),
            balance_due=Decimal("10"),
            invoice_number="INV-1",
            invoice_date=None,
            order=None,
        ),
        SimpleNamespace(
            currency="AED",
            exchange_rate=Decimal("1"),
            total_amount=Decimal("105"),
            tax_amount=Decimal("5"),
            paid_amount=Decimal("50"),
            balance_due=Decimal("55"),
            invoice_number="INV-2",
            invoice_date=None,
            order=None,
        ),
    ]
    query = mocker.MagicMock()
    query.filter_by.return_value = query
    query.all.return_value = invoices
    mocker.patch("services.maintenance_order_service.tenant_query", return_value=query)
    mocker.patch("services.maintenance_order_service.get_active_tenant_id", return_value=None)
    mocker.patch("services.maintenance_order_service.resolve_tenant_base_currency", return_value="AED")

    report = MaintenanceService.get_revenue_report(7, date_from=None, date_to=None)

    query.filter_by.assert_called_once_with(tenant_id=7, posted=True, gl_posted=True)
    assert report["base_currency"] == "AED"
    assert report["total_gross"] == Decimal("325.000")
    assert report["total_tax"] == Decimal("25.000")
    assert report["total_revenue"] == Decimal("300.000")
    assert report["total_paid"] == Decimal("250.000")
    assert report["total_due"] == Decimal("75.000")


@pytest.mark.parametrize(
    "call",
    [
        lambda: _without_document(MaintenanceService._create_receipt, None, 1, Decimal("1"), "cash", None),
        lambda: _without_document(MaintenanceService._create_invoice, None),
        lambda: _without_document(MaintenanceGLService.post_invoice, None, 1),
        lambda: _without_document(MaintenanceGLService.post_receipt, None, 1),
        lambda: _without_document(MaintenanceGLService.post_deposit, None, 1),
        lambda: _without_document(MaintenanceGLService.post_deposit_application, None, 1),
        lambda: _without_document(MaintenanceGLService.post_parts_cost, None, Decimal("1"), 1),
        lambda: _without_document(MaintenanceGLService.post_return, None, 1),
        lambda: _without_document(MaintenanceStockService.consume_parts_for_order_line, None, 1),
        lambda: _without_document(MaintenanceStockService.return_parts_for_return_line, None, 1),
    ],
)
def test_financial_operations_without_a_document_fail_closed(call):
    """A posting without a real document must refuse, not write a broken row."""
    with pytest.raises(ValueError):
        call()


def test_warranty_requires_active_dated_coverage_and_accepts_naive_dates():
    now = datetime.now(UTC)
    device = MaintenanceDeviceRegistry(is_active=True, is_under_warranty=True)
    assert device.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN
    device.warranty_end_date = (now + timedelta(days=1)).replace(tzinfo=None)
    assert device.warranty_status == MaintenanceOrderWarrantyStatus.UNDER_WARRANTY
    device.warranty_start_date = now + timedelta(hours=1)
    assert device.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN
    device.warranty_start_date = None
    device.warranty_end_date = (now - timedelta(days=1)).replace(tzinfo=None)
    assert device.warranty_status == MaintenanceOrderWarrantyStatus.EXPIRED
    device.is_active = False
    assert device.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN


def test_warranty_audit_is_append_only_in_database(db_session, sample_tenant, sample_user):
    audit = MaintenanceWarrantyAudit(
        tenant_id=sample_tenant.id,
        action="checked",
        to_status="unknown",
        performed_by=sample_user.id,
    )
    db_session.add(audit)
    db_session.flush()
    for statement in (
        "UPDATE maintenance_warranty_audit SET to_status = 'void' WHERE id = :id",
        "DELETE FROM maintenance_warranty_audit WHERE id = :id",
    ):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(text(statement), {"id": audit.id})
    assert db_session.get(MaintenanceWarrantyAudit, audit.id).to_status == "unknown"


def test_sqlite_maintenance_audit_and_archive_guards():
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = import_module("migrations.versions.m3a4b5c6d7e8_maintenance_module")
    tables = (
        "maintenance_orders",
        "maintenance_order_lines",
        "maintenance_order_services",
        "maintenance_order_status_logs",
        "maintenance_receipts",
        "maintenance_invoices",
        "maintenance_returns",
        "maintenance_return_lines",
        "maintenance_services",
        "maintenance_device_registry",
        "maintenance_warranty_audit",
    )
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            for table in tables:
                connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, detail TEXT)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration._install_warranty_audit_guards()
                migration._install_archive_only_guards()
            for table in ("maintenance_orders", "maintenance_order_status_logs", "maintenance_warranty_audit"):
                connection.execute(text(f"INSERT INTO {table} (id, detail) VALUES (1, 'original')"))
                with pytest.raises(DBAPIError):
                    connection.execute(text(f"DELETE FROM {table} WHERE id = 1"))
            for table in ("maintenance_order_status_logs", "maintenance_warranty_audit"):
                with pytest.raises(DBAPIError):
                    connection.execute(text(f"UPDATE {table} SET detail = 'modified' WHERE id = 1"))
    finally:
        engine.dispose()


def test_migration_columns_and_gl_allowlist_match_models(db_session):
    from extensions import db

    inspector = inspect(db_session.get_bind())
    for name, table in db.metadata.tables.items():
        if name.startswith("maintenance_"):
            assert {c["name"] for c in inspector.get_columns(name)} == set(table.columns.keys()), name
    checks = inspector.get_check_constraints("gl_account_mappings")
    concept_check = next(c["sqltext"] for c in checks if c["name"] == "ck_gl_account_mappings_concept_code")
    assert "MAINTENANCE_AR" in concept_check
    assert "MAINTENANCE_REVENUE" in concept_check


def test_create_rejects_another_tenants_branch(db_session, sample_tenant, sample_user, sample_branch):
    from uuid import uuid4

    from models import Tenant
    from utils.tenanting import without_tenant_scope

    with without_tenant_scope():
        other = Tenant(name="Maintenance isolation", name_ar="عزل", slug=f"maintenance-{uuid4().hex[:8]}", country="AE")
        db_session.add(other)
        db_session.flush()
    with pytest.raises(ValueError, match="الفرع غير موجود"):
        MaintenanceService.create_order(
            tenant_id=other.id,
            branch_id=sample_branch.id,
            warehouse_id=None,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )


def test_ready_requires_warranty_check(db_session, sample_tenant, sample_user, sample_warehouse):
    order = MaintenanceService.create_order(
        tenant_id=sample_tenant.id,
        branch_id=sample_warehouse.branch_id,
        warehouse_id=sample_warehouse.id,
        customer_id=None,
        customer_name=None,
        customer_phone=None,
        device_brand=None,
        device_model=None,
        device_serial_number="NOT-IN-REGISTRY",
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description=None,
        received_by=sample_user.id,
    )
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("DELETE FROM maintenance_orders WHERE id = :id"), {"id": order.id})
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE maintenance_order_status_logs SET to_status = 'closed' WHERE order_id = :id"), {"id": order.id}
        )
    for status in ("diagnosis", "in_progress"):
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id)
    with pytest.raises(ValueError, match="فحص الكفالة"):
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)
    MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
    MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)
    assert order.status == "ready"
    assert order.warranty_status == "unknown"


def test_product_rate_and_price_cannot_be_changed_without_authorization(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_product
):
    order = MaintenanceService.create_order(
        tenant_id=sample_tenant.id,
        branch_id=sample_warehouse.branch_id,
        warehouse_id=sample_warehouse.id,
        customer_id=None,
        customer_name=None,
        customer_phone=None,
        device_brand=None,
        device_model=None,
        device_serial_number=None,
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description=None,
        received_by=sample_user.id,
    )
    args = dict(
        order_id=order.id,
        tenant_id=sample_tenant.id,
        product_id=sample_product.id,
        quantity=Decimal("1"),
        warehouse_id=sample_warehouse.id,
    )
    with pytest.raises(ValueError, match="الضريبة"):
        MaintenanceService.add_line(**args, unit_price=Decimal("100"), tax_rate=Decimal("0"))
    with pytest.raises(ValueError, match="السعر"):
        MaintenanceService.add_line(**args, unit_price=Decimal("50"))
    line = MaintenanceService.add_line(**args, unit_price=Decimal("100"))
    assert line.tax_rate == Decimal("5")
    assert line.tax_amount == Decimal("5.000")


def test_warranty_cancel_and_restore_are_authorized_and_persisted(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, mocker
):
    now = datetime.now(UTC)
    device = MaintenanceDeviceRegistry(
        tenant_id=sample_tenant.id,
        customer_id=sample_customer.id,
        serial_number="WARRANTY-CANCEL-TEST",
        warranty_start_date=now - timedelta(days=1),
        warranty_end_date=now + timedelta(days=30),
        is_under_warranty=True,
        is_active=True,
    )
    db_session.add(device)
    db_session.flush()
    order = MaintenanceService.create_order(
        tenant_id=sample_tenant.id,
        branch_id=sample_warehouse.branch_id,
        warehouse_id=sample_warehouse.id,
        customer_id=sample_customer.id,
        customer_name=None,
        customer_phone=None,
        device_brand=None,
        device_model=None,
        device_serial_number=device.serial_number,
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description=None,
        received_by=sample_user.id,
    )
    MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
    assert order.warranty_status == "under_warranty"

    permission = mocker.patch.object(sample_user, "has_permission", return_value=False)
    with pytest.raises(ValueError, match="صلاحية"):
        WarrantyService.cancel_warranty(order.id, sample_tenant.id, performed_by=sample_user.id, reason="damage")
    permission.return_value = True
    with pytest.raises(ValueError, match="سبب"):
        WarrantyService.cancel_warranty(order.id, sample_tenant.id, performed_by=sample_user.id, reason="")

    cancelled = WarrantyService.cancel_warranty(
        order.id, sample_tenant.id, performed_by=sample_user.id, reason="damage"
    )
    assert cancelled.action == "cancelled"
    assert device.is_under_warranty is False
    MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
    assert order.warranty_status == "void"
    restored = WarrantyService.restore_warranty(
        order.id, sample_tenant.id, performed_by=sample_user.id, reason="cancellation reversed"
    )
    assert restored.action == "restored"
    assert device.is_under_warranty is True
    assert order.warranty_status == "under_warranty"
