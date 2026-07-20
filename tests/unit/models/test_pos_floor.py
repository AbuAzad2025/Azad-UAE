"""Unit tests for models/pos_floor.py — PosFloor, PosTable, PosTableOrder."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


class TestPosFloor:
    def test_create_with_defaults(self, db_session, sample_tenant):
        from models.pos_floor import PosFloor

        floor = PosFloor(tenant_id=sample_tenant.id, name="Main Hall")
        db_session.add(floor)
        db_session.commit()

        assert floor.id is not None
        assert floor.name_ar is None
        assert floor.sort_order == 0
        assert floor.is_active is True

    def test_name_is_required(self, db_session, sample_tenant):
        from models.pos_floor import PosFloor

        db_session.add(PosFloor(tenant_id=sample_tenant.id, name=None))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_tables_relationship_ordered_and_dynamic(self, db_session, sample_tenant):
        from models.pos_floor import PosFloor, PosTable

        floor = PosFloor(tenant_id=sample_tenant.id, name="Terrace")
        db_session.add(floor)
        db_session.flush()
        db_session.add_all(
            [
                PosTable(
                    tenant_id=sample_tenant.id,
                    floor_id=floor.id,
                    label="T2",
                    sort_order=2,
                ),
                PosTable(
                    tenant_id=sample_tenant.id,
                    floor_id=floor.id,
                    label="T1",
                    sort_order=1,
                ),
            ]
        )
        db_session.commit()

        # lazy="dynamic" exposes a query object, ordered by PosTable.sort_order
        assert floor.tables.count() == 2
        assert [t.label for t in floor.tables.all()] == ["T1", "T2"]
        assert floor.tables.first().floor is floor


class TestPosTable:
    def test_create_with_defaults(self, db_session, sample_tenant):
        from models.pos_floor import PosFloor, PosTable

        floor = PosFloor(tenant_id=sample_tenant.id, name="F1")
        db_session.add(floor)
        db_session.flush()
        table = PosTable(tenant_id=sample_tenant.id, floor_id=floor.id, label="A1")
        db_session.add(table)
        db_session.commit()

        assert table.capacity == 4
        assert table.pos_x == 0
        assert table.pos_y == 0
        assert table.shape == "rectangle"
        assert table.status == "free"
        assert table.sort_order == 0
        assert table.is_active is True

    def test_floor_id_is_required(self, db_session, sample_tenant):
        from models.pos_floor import PosTable

        db_session.add(PosTable(tenant_id=sample_tenant.id, label="A9"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestPosTableOrder:
    def test_create_with_defaults(self, db_session, sample_tenant, sample_sale):
        from models.pos_floor import PosFloor, PosTable, PosTableOrder

        floor = PosFloor(tenant_id=sample_tenant.id, name="F1")
        db_session.add(floor)
        db_session.flush()
        table = PosTable(tenant_id=sample_tenant.id, floor_id=floor.id, label="A1")
        db_session.add(table)
        db_session.flush()

        order = PosTableOrder(
            tenant_id=sample_tenant.id, table_id=table.id, sale_id=sample_sale.id
        )
        db_session.add(order)
        db_session.commit()

        assert order.id is not None
        assert order.guest_count == 1
        assert order.is_split is False
        assert order.split_group is None
        assert order.created_at is not None

    def test_split_group_persisted(self, db_session, sample_tenant, sample_sale):
        from models.pos_floor import PosFloor, PosTable, PosTableOrder

        floor = PosFloor(tenant_id=sample_tenant.id, name="F1")
        db_session.add(floor)
        db_session.flush()
        table = PosTable(tenant_id=sample_tenant.id, floor_id=floor.id, label="A1")
        db_session.add(table)
        db_session.flush()

        order = PosTableOrder(
            tenant_id=sample_tenant.id,
            table_id=table.id,
            sale_id=sample_sale.id,
            guest_count=4,
            is_split=True,
            split_group="G-1",
        )
        db_session.add(order)
        db_session.commit()
        db_session.expire_all()

        refreshed = type(order).query.get(order.id)
        assert refreshed.guest_count == 4
        assert refreshed.is_split is True
        assert refreshed.split_group == "G-1"
