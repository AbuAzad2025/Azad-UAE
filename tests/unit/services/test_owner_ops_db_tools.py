"""OwnerOpsService — super-admin DB tools, dashboard admin map, lookups.

The raw-SQL helpers accept a ``db=`` seam; tests bind that seam to the real
test-database session/engine and exercise them against a scratch table so no
production table is ever mutated.  The scratch table is committed because
PostgreSQL inspector calls open their own connection.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text as sa_text

from extensions import db
from services.owner_ops_service import OwnerOpsService


@pytest.fixture
def seam(db_session, app):
    with app.app_context():
        yield SimpleNamespace(session=db_session, engine=db.engine)


@pytest.fixture
def scratch_table(db_session):
    """Committed scratch table dropped again at teardown."""

    name = f"covf_scratch_{uuid.uuid4().hex[:8]}"
    db_session.execute(sa_text(f'CREATE TABLE "{name}" (id serial primary key, label text)'))
    for i in range(1, 4):
        db_session.execute(sa_text(f'INSERT INTO "{name}" (label) VALUES (:l)'), {"l": f"row{i}"})
    db_session.commit()
    yield name
    try:
        db_session.rollback()
        db_session.execute(sa_text(f'DROP TABLE IF EXISTS "{name}"'))
        db_session.commit()
    except Exception:
        db_session.rollback()


class TestDatabaseToolsAgainstScratchTable:
    def test_table_row_count(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        assert OwnerOpsService.table_row_count(scratch_table, db=seam) == 3

    def test_run_select_rows_returns_dicts(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        data, count = OwnerOpsService.run_select_rows(f"SELECT id, label FROM {scratch_table} ORDER BY id", db=seam)
        assert count == 3
        assert [d["label"] for d in data] == ["row1", "row2", "row3"]

    def test_truncate_table_rows_wipes_all(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        OwnerOpsService.truncate_table_rows(scratch_table, db=seam)
        seam.session.commit()
        assert OwnerOpsService.table_row_count(scratch_table, db=seam) == 0

    def test_select_table_page_paging_and_keys(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        page1_rows, keys = OwnerOpsService.select_table_page(scratch_table, page=1, per_page=2, db=seam)
        assert len(page1_rows) == 2
        assert set(keys) >= {"id", "label"}

        page2_rows, _ = OwnerOpsService.select_table_page(scratch_table, page=2, per_page=2, db=seam)
        assert len(page2_rows) == 1

    def test_select_table_rows_limit(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        rows, keys = OwnerOpsService.select_table_rows(scratch_table, limit=2, db=seam)
        assert len(rows) == 2
        assert set(keys) >= {"id", "label"}

    def test_select_table_result_raw_cursor(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        result = OwnerOpsService.select_table_result(scratch_table, db=seam)
        rows = result.fetchall()
        assert len(rows) == 3

    def test_execute_table_row_update_mutates_target_row(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        target_id = seam.session.execute(sa_text(f'SELECT id FROM "{scratch_table}" ORDER BY id LIMIT 1')).scalar()
        OwnerOpsService.execute_table_row_update(scratch_table, "id", target_id, {"label": "patched"}, db=seam)
        seam.session.commit()

        label = seam.session.execute(
            sa_text(f'SELECT label FROM "{scratch_table}" WHERE id = :i'), {"i": target_id}
        ).scalar()
        assert label == "patched"

    def test_run_select_matrix_shape(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        matrix = OwnerOpsService.run_select_matrix(f"SELECT id, label FROM {scratch_table} ORDER BY id", db=seam)
        assert matrix["columns"] == ["id", "label"]
        assert matrix["count"] == 3
        assert matrix["rows"][0][1] == "row1"

    def test_export_tables_data_keyed_dump(self, seam, scratch_table):
        from services.owner_ops_service import OwnerOpsService

        export = OwnerOpsService.export_tables_data([scratch_table], db=seam)
        assert set(export.keys()) == {scratch_table}
        assert len(export[scratch_table]) == 3
        assert all("label" in row for row in export[scratch_table])

    def test_table_columns_and_pk_on_real_table(self, seam):
        from services.owner_ops_service import OwnerOpsService

        columns, pk_cols = OwnerOpsService.table_columns_and_pk("tenants", db=seam)
        assert "slug" in columns
        assert pk_cols == ["id"]


class TestSuperAdminDashboardAdminMap:
    def test_admin_emails_map_tenant_to_first_super_admin(self, db_session, sample_tenant, sample_role):
        from models.user import User

        suffix = uuid.uuid4().hex[:8]
        admin = User(
            username=f"sa-{suffix}",
            email=f"sa-{suffix}@example.com",
            full_name="SA",
            tenant_id=sample_tenant.id,
            role_id=sample_role.id,
        )
        admin.set_password("password123")
        db_session.add(admin)
        db_session.flush()

        ctx = OwnerOpsService.landlord_dashboard_context()
        assert ctx["admin_emails"].get(sample_tenant.id) == admin.email


class TestSimpleLookups:
    def test_get_user_roundtrip_and_miss(self, db_session, sample_user):
        from services.owner_ops_service import OwnerOpsService

        assert OwnerOpsService.get_user(sample_user.id).id == sample_user.id
        assert OwnerOpsService.get_user(999999999) is None

    def test_get_store_payment_method_accepts_string_id(self, db_session, sample_tenant):
        from models.store_payment_method import StorePaymentMethod
        from services.owner_ops_service import OwnerOpsService

        suffix = uuid.uuid4().hex[:8]
        method = StorePaymentMethod(
            tenant_id=sample_tenant.id,
            code=f"pm_{suffix}",
            name_ar="طريقة دفع",
            name_en="Payment Method",
        )
        db_session.add(method)
        db_session.flush()

        found = OwnerOpsService.get_store_payment_method(str(method.id))
        assert found.id == method.id
        assert OwnerOpsService.get_store_payment_method(999999999) is None
