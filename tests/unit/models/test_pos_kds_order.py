"""Unit tests for models/pos_kds_order.py — PosKdsOrder kitchen-display orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def kds_order(db_session, sample_tenant, sample_sale):
    from models.pos_kds_order import PosKdsOrder

    order = PosKdsOrder(
        tenant_id=sample_tenant.id,
        sale_id=sample_sale.id,
        order_number=sample_sale.sale_number,
        items_json=json.dumps([{"name": "Burger", "quantity": 2}]),
    )
    db_session.add(order)
    db_session.commit()
    return order


class TestPosKdsOrderDefaults:
    def test_defaults_on_create(self, kds_order):
        assert kds_order.id is not None
        assert kds_order.status == "pending"
        assert kds_order.priority == 0
        assert kds_order.completed_at is None
        assert kds_order.created_at is not None
        assert kds_order.updated_at is not None

    def test_optional_fks_default_to_none(self, kds_order):
        assert kds_order.session_id is None
        assert kds_order.branch_id is None

    def test_items_json_round_trip(self, kds_order):
        items = json.loads(kds_order.items_json)
        assert items == [{"name": "Burger", "quantity": 2}]

    def test_sale_relationship(self, kds_order, sample_sale):
        assert kds_order.sale is not None
        assert kds_order.sale.id == sample_sale.id


class TestPosKdsOrderConstraints:
    def test_items_json_required(self, db_session, sample_tenant, sample_sale):
        from models.pos_kds_order import PosKdsOrder

        db_session.add(
            PosKdsOrder(
                tenant_id=sample_tenant.id,
                sale_id=sample_sale.id,
                order_number="S-X",
                items_json=None,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_order_number_required(self, db_session, sample_tenant, sample_sale):
        from models.pos_kds_order import PosKdsOrder

        db_session.add(
            PosKdsOrder(
                tenant_id=sample_tenant.id,
                sale_id=sample_sale.id,
                order_number=None,
                items_json="[]",
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestPosKdsOrderLifecycle:
    def test_completion_persists(self, db_session, kds_order):
        kds_order.status = "done"
        kds_order.completed_at = datetime.now(timezone.utc)
        db_session.commit()
        db_session.expire_all()

        refreshed = type(kds_order).query.get(kds_order.id)
        assert refreshed.status == "done"
        assert refreshed.completed_at is not None
