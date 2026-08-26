"""PosWriteService — real-DB behavioral coverage.

Every create* helper must persist a tenant-scoped row with flush-only
semantics (callers own the transaction); the scoped fetches must honor
tenant isolation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from models import (
    PosFloor,
    PosKdsOrder,
    PosOrderType,
    PosPrinter,
    PosTable,
    PosTableOrder,
    SystemSettings,
)


@pytest.fixture
def floor(db_session, sample_tenant):
    floor = PosFloor(tenant_id=sample_tenant.id, name="Ground", name_ar="الأرضي")
    db_session.add(floor)
    db_session.flush()
    return floor


@pytest.fixture
def table(db_session, sample_tenant, floor):
    table = PosTable(tenant_id=sample_tenant.id, floor_id=floor.id, label="T1", capacity=4)
    db_session.add(table)
    db_session.flush()
    return table


class TestCreateOrderType:
    def test_creates_active_order_type_with_defaults(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        ot = PosWriteService.create_order_type(
            tenant_id=sample_tenant.id, code="dine_in", name_ar="صالة", name_en="Dine In"
        )
        db_session.flush()

        stored = db_session.get(PosOrderType, ot.id)
        assert stored is not None
        assert stored.tenant_id == sample_tenant.id
        assert stored.code == "dine_in"
        assert stored.name_ar == "صالة"
        assert stored.name_en == "Dine In"
        assert stored.is_active is True
        assert stored.is_default is False
        assert stored.kds_enabled is False
        assert stored.sort_order == 0

    def test_blank_names_fall_back_to_code_and_null_english(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        ot = PosWriteService.create_order_type(tenant_id=sample_tenant.id, code="takeaway")
        db_session.flush()
        assert ot.name_ar == "takeaway"
        assert ot.name_en is None

    def test_duplicate_code_rejected_within_tenant(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        PosWriteService.create_order_type(tenant_id=sample_tenant.id, code="dup")
        db_session.flush()
        with pytest.raises(ValueError, match="موجود مسبقاً"):
            PosWriteService.create_order_type(tenant_id=sample_tenant.id, code="dup")

    def test_same_code_allowed_for_other_tenants(self, db_session, sample_tenant, other_tenant):
        from services.pos_write_service import PosWriteService

        PosWriteService.create_order_type(tenant_id=sample_tenant.id, code="shared")
        ot2 = PosWriteService.create_order_type(tenant_id=other_tenant.id, code="shared")
        db_session.flush()
        assert ot2.id is not None

    def test_delete_order_type_removes_row(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        ot = PosWriteService.create_order_type(tenant_id=sample_tenant.id, code="gone")
        db_session.flush()
        ot_id = ot.id

        PosWriteService.delete_order_type(ot)
        db_session.flush()
        assert db_session.get(PosOrderType, ot_id) is None


@pytest.fixture
def other_tenant(db_session):
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Rival Co {unique}",
        name_ar="منافس",
        slug=f"rival-{unique}",
        email=f"rival-{unique}@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


class TestCreateFloorAndTable:
    def test_create_floor_persists_floor(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        floor = PosWriteService.create_floor(tenant_id=sample_tenant.id, name="First", name_ar="أول")
        db_session.flush()

        stored = db_session.get(PosFloor, floor.id)
        assert stored is not None
        assert stored.tenant_id == sample_tenant.id
        assert stored.name == "First"
        assert stored.name_ar == "أول"
        assert stored.is_active is True

    def test_create_table_maps_name_to_label_and_seats_to_capacity(self, db_session, sample_tenant, floor):
        """Regression: service used to pass nonexistent ``name``/``seats``
        kwargs which crashed every table creation with TypeError."""
        from services.pos_write_service import PosWriteService

        table = PosWriteService.create_table(
            tenant_id=sample_tenant.id,
            floor_id=floor.id,
            name="T7",
            seats=6,
            pos_x=12,
            pos_y=30,
        )
        db_session.flush()

        stored = db_session.get(PosTable, table.id)
        assert stored is not None
        assert stored.tenant_id == sample_tenant.id
        assert stored.floor_id == floor.id
        assert stored.label == "T7"
        assert stored.capacity == 6
        assert (stored.pos_x, stored.pos_y) == (12, 30)
        assert stored.is_active is True


class TestTableAndKdsOrders:
    def test_create_table_order_model_links_sale(self, db_session, sample_tenant, table, sample_sale):
        from services.pos_write_service import PosWriteService

        torder = PosWriteService.create_table_order_model(
            tenant_id=sample_tenant.id,
            table_id=table.id,
            sale_id=sample_sale.id,
            guest_count=4,
        )
        db_session.flush()

        stored = db_session.get(PosTableOrder, torder.id)
        assert stored is not None
        assert stored.table_id == table.id
        assert stored.sale_id == sample_sale.id
        assert stored.guest_count == 4

    def test_create_kds_order_starts_pending_with_payload(
        self, db_session, sample_tenant, sample_sale, pos_open_session
    ):
        from services.pos_write_service import PosWriteService

        kds = PosWriteService.create_kds_order(
            tenant_id=sample_tenant.id,
            sale_id=sample_sale.id,
            session_id=pos_open_session.id,
            order_number="KDS-1",
            items_json='[{"product_id": 1, "qty": 2}]',
            notes="no onions",
        )
        db_session.flush()

        stored = db_session.get(PosKdsOrder, kds.id)
        assert stored is not None
        assert stored.status == "pending"
        assert stored.sale_id == sample_sale.id
        assert stored.session_id == pos_open_session.id
        assert stored.items_json == '[{"product_id": 1, "qty": 2}]'
        assert stored.notes == "no onions"
        assert stored.completed_at is None

    def test_kds_order_for_sale_is_tenant_scoped(self, db_session, sample_tenant, other_tenant, sample_sale):
        from services.pos_write_service import PosWriteService

        kds = PosWriteService.create_kds_order(tenant_id=sample_tenant.id, sale_id=sample_sale.id, order_number="KDS-2")
        db_session.flush()

        found = PosWriteService.kds_order_for_sale(sample_sale.id, sample_tenant.id)
        assert found is not None
        assert found.id == kds.id
        # A different tenant cannot see it even with the sale id.
        assert PosWriteService.kds_order_for_sale(sample_sale.id, other_tenant.id) is None


@pytest.fixture
def pos_open_session(db_session, sample_tenant, sample_branch, sample_user):
    from models import PosSession

    session = PosSession(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        session_number=f"POS-SES-{uuid.uuid4().hex[:8]}",
        status="open",
    )
    db_session.add(session)
    db_session.flush()
    return session


class TestPrinters:
    def test_create_printer_defaults(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        printer = PosWriteService.create_printer(tenant_id=sample_tenant.id, name="Front Desk")
        db_session.flush()

        stored = db_session.get(PosPrinter, printer.id)
        assert stored is not None
        assert stored.role == "customer"
        assert stored.connection_type == "agent_network"
        assert stored.encoding == "cp864"
        assert list(stored.categories) == []
        assert stored.is_active is True
        assert stored.host is None and stored.port is None

    def test_create_printer_kitchen_with_categories(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        printer = PosWriteService.create_printer(
            tenant_id=sample_tenant.id,
            name="Kitchen 1",
            role="kitchen",
            connection_type="agent_serial",
            serial_port="COM3",
            baud_rate=9600,
            category_ids=[5, 9],
            sort_order=3,
        )
        db_session.flush()

        stored = db_session.get(PosPrinter, printer.id)
        assert stored.role == "kitchen"
        assert stored.serial_port == "COM3"
        assert stored.baud_rate == 9600
        assert stored.covers_category(5) is True
        assert stored.covers_category(7) is False

    def test_delete_printer_removes_row(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        printer = PosWriteService.create_printer(tenant_id=sample_tenant.id, name="Old")
        db_session.flush()
        pid = printer.id

        PosWriteService.delete_printer(printer)
        db_session.flush()
        assert db_session.get(PosPrinter, pid) is None


class TestScopedFetches:
    def test_latest_system_settings_returns_newest_row(self, db_session):
        from services.pos_write_service import PosWriteService

        first = SystemSettings(system_name="old-name")
        db_session.add(first)
        db_session.flush()

        latest = PosWriteService.latest_system_settings()
        assert latest is not None
        assert latest.id >= first.id

        second = SystemSettings(system_name="newer-name")
        db_session.add(second)
        db_session.flush()
        assert PosWriteService.latest_system_settings().id == second.id

    def test_products_by_ids_scoped_to_tenant(self, db_session, sample_tenant, other_tenant):
        from models import Product
        from services.pos_write_service import PosWriteService

        mine = Product(
            tenant_id=sample_tenant.id,
            name="Mine",
            sku=f"M-{uuid.uuid4().hex[:6]}",
            cost_price=Decimal("1"),
            regular_price=Decimal("2"),
        )
        theirs = Product(
            tenant_id=other_tenant.id,
            name="Theirs",
            sku=f"T-{uuid.uuid4().hex[:6]}",
            cost_price=Decimal("1"),
            regular_price=Decimal("2"),
        )
        db_session.add_all([mine, theirs])
        db_session.flush()

        result = PosWriteService.products_by_ids([mine.id, theirs.id], sample_tenant.id)
        assert set(result.keys()) == {mine.id}
        assert result[mine.id].name == "Mine"

    def test_products_by_ids_empty_when_no_match(self, db_session, sample_tenant):
        from services.pos_write_service import PosWriteService

        assert PosWriteService.products_by_ids([999999], sample_tenant.id) == {}

    def test_session_sales_scoped_to_tenant_and_session(
        self, db_session, sample_tenant, other_tenant, pos_open_session, sample_customer, sample_user
    ):
        from datetime import UTC, datetime

        from models import Sale
        from services.pos_write_service import PosWriteService

        s1 = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"SAL-A-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("10"),
            total_amount=Decimal("11"),
            amount=Decimal("11"),
            amount_aed=Decimal("11"),
            balance_due=Decimal("0"),
            currency="AED",
            pos_session_id=pos_open_session.id,
        )
        # Same session id but foreign tenant — must never leak.
        s2 = Sale(
            tenant_id=other_tenant.id,
            sale_number=f"SAL-B-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("5"),
            total_amount=Decimal("6"),
            amount=Decimal("6"),
            amount_aed=Decimal("6"),
            balance_due=Decimal("0"),
            currency="AED",
            pos_session_id=pos_open_session.id,
        )
        db_session.add_all([s1, s2])
        db_session.flush()

        sales = PosWriteService.session_sales(sample_tenant.id, pos_open_session.id)
        assert [s.id for s in sales] == [s1.id]

    def test_recent_session_sales_orders_desc_and_limits(
        self, db_session, sample_tenant, pos_open_session, sample_customer, sample_user
    ):
        from datetime import UTC, datetime, timedelta

        from models import Sale
        from services.pos_write_service import PosWriteService

        base = datetime.now(UTC)
        sales = []
        for i in range(3):
            s = Sale(
                tenant_id=sample_tenant.id,
                sale_number=f"SAL-R{i}-{uuid.uuid4().hex[:6]}",
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                sale_date=base + timedelta(minutes=i),
                subtotal=Decimal("1"),
                total_amount=Decimal("1"),
                amount=Decimal("1"),
                amount_aed=Decimal("1"),
                balance_due=Decimal("0"),
                currency="AED",
                pos_session_id=pos_open_session.id,
            )
            sales.append(s)
        db_session.add_all(sales)
        db_session.flush()

        recent = PosWriteService.recent_session_sales(sample_tenant.id, pos_open_session.id, limit=2)
        assert [s.id for s in recent] == [sales[2].id, sales[1].id]

        # Other sessions contribute nothing.
        assert PosWriteService.recent_session_sales(sample_tenant.id, 987654) == []

    def test_shift_cash_movements_scoped_to_tenant_and_shift(
        self, db_session, sample_tenant, other_tenant, pos_open_session, sample_branch, sample_user
    ):
        from decimal import Decimal

        from models import PosCashMovement, PosShift
        from services.pos_write_service import PosWriteService

        shift = PosShift(
            tenant_id=sample_tenant.id,
            session_id=pos_open_session.id,
            user_id=sample_user.id,
            shift_number=f"SHF-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(shift)
        db_session.flush()

        pay_in = PosCashMovement(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_id=pos_open_session.id,
            shift_id=shift.id,
            movement_type=PosCashMovement.TYPE_PAY_IN,
            amount=Decimal("100.000"),
            reason="float top-up",
        )
        foreign = PosCashMovement(
            tenant_id=other_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_id=pos_open_session.id,
            shift_id=shift.id,
            movement_type=PosCashMovement.TYPE_PAY_IN,
            amount=Decimal("999.000"),
            reason="foreign probe",
        )
        db_session.add_all([pay_in, foreign])
        db_session.flush()

        movements = PosWriteService.shift_cash_movements(sample_tenant.id, shift.id)
        assert [m.id for m in movements] == [pay_in.id]
