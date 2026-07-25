from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from models import Product, StockMovement, Tenant, Warehouse
from services.stock_service import StockService

_BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _add_movement(db_session, tenant_id, product_id, warehouse_id, movement_type, quantity, minutes):
    movement = StockMovement(
        tenant_id=tenant_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        quantity=Decimal(str(quantity)),
        created_at=_BASE_TIME + timedelta(minutes=minutes),
    )
    db_session.add(movement)
    db_session.flush()
    return movement


def _add_product(db_session, tenant_id, name):
    product = Product(
        tenant_id=tenant_id,
        name=name,
        sku=f"SKU-RB-{uuid.uuid4().hex[:8]}",
        cost_price=Decimal("10.000"),
        regular_price=Decimal("20.000"),
        current_stock=Decimal("0.000"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def _add_warehouse(db_session, tenant_id, branch_id, name):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        branch_id=branch_id,
        name=name,
        is_active=True,
    )
    db_session.add(warehouse)
    db_session.flush()
    return warehouse


def _add_tenant(db_session):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Company {unique}",
        name_ar="شركة أخرى",
        slug=f"other-company-{unique}",
        email=f"other-{unique}@example.com",
        phone_1="0500000001",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


class TestGetMovementRunningBalances:
    def test_signed_sequence_before_after_per_movement(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        m1 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 10, 0)
        m2 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "out", -3, 1)
        m3 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 5, 2)
        m4 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "out", -2, 3)

        balances = StockService.get_movement_running_balances([m1, m2, m3, m4], sample_tenant.id)

        assert balances[m1.id] == (Decimal("0"), Decimal("10"))
        assert balances[m2.id] == (Decimal("10"), Decimal("7"))
        assert balances[m3.id] == (Decimal("7"), Decimal("12"))
        assert balances[m4.id] == (Decimal("12"), Decimal("10"))

    def test_window_spans_full_history_not_just_page(self, db_session, sample_tenant, sample_product, sample_warehouse):
        m1 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 10, 0)
        m2 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "out", -3, 1)
        m3 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 5, 2)

        balances = StockService.get_movement_running_balances([m3], sample_tenant.id)

        assert m1.id not in balances
        assert m2.id not in balances
        assert balances[m3.id] == (Decimal("7"), Decimal("12"))

    def test_distinct_pairs_do_not_mix(
        self, db_session, sample_tenant, sample_branch, sample_product, sample_warehouse
    ):
        other_product = _add_product(db_session, sample_tenant.id, "Second Product")
        other_warehouse = _add_warehouse(db_session, sample_tenant.id, sample_branch.id, "Second Warehouse")

        a1 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 10, 0)
        b1 = _add_movement(db_session, sample_tenant.id, other_product.id, other_warehouse.id, "in", 100, 1)
        a2 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "out", -3, 2)
        b2 = _add_movement(db_session, sample_tenant.id, other_product.id, other_warehouse.id, "out", -50, 3)

        balances = StockService.get_movement_running_balances([a1, b1, a2, b2], sample_tenant.id)

        assert balances[a1.id] == (Decimal("0"), Decimal("10"))
        assert balances[a2.id] == (Decimal("10"), Decimal("7"))
        assert balances[b1.id] == (Decimal("0"), Decimal("100"))
        assert balances[b2.id] == (Decimal("100"), Decimal("50"))

    def test_tenant_isolation_excludes_foreign_rows(self, db_session, sample_tenant, sample_product, sample_warehouse):
        other_tenant = _add_tenant(db_session)
        m1 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "in", 10, 0)
        rogue = _add_movement(db_session, other_tenant.id, sample_product.id, sample_warehouse.id, "in", 1000, 1)
        m2 = _add_movement(db_session, sample_tenant.id, sample_product.id, sample_warehouse.id, "out", -3, 2)

        balances = StockService.get_movement_running_balances([m1, m2], sample_tenant.id)

        assert balances[m1.id] == (Decimal("0"), Decimal("10"))
        assert balances[m2.id] == (Decimal("10"), Decimal("7"))
        assert rogue.id not in balances

        wrong_tenant = StockService.get_movement_running_balances([m1, m2], other_tenant.id)
        assert wrong_tenant == {}

    def test_empty_input_returns_empty_dict(self, db_session, sample_tenant):
        assert StockService.get_movement_running_balances([], sample_tenant.id) == {}
        assert StockService.get_movement_running_balances(None, sample_tenant.id) == {}
