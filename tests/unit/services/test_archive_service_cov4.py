"""Cov4: archive_service — to_dict/non-dict/no-tenant/soft/hard/restore/query/cleanup arcs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.archive_service import ArchiveService


def test_archive_record_with_to_dict(db_session, sample_tenant):
    rec = SimpleNamespace(id=5, tenant_id=sample_tenant.id,
                          to_dict=lambda: {"id": 5, "x": 1})
    out = ArchiveService.archive_record("sales", rec, reason="cov4")
    assert out.table_name == "sales"
    assert out.data == {"id": 5, "x": 1}


def test_archive_record_without_to_dict_uses_columns(db_session, sample_customer):
    out = ArchiveService.archive_record("customers", sample_customer)
    assert out.record_id == sample_customer.id
    assert out.data["name"] == sample_customer.name


def test_archive_record_without_tenant_raises():
    rec = SimpleNamespace(id=1, __table__=SimpleNamespace(columns=[]))
    with pytest.raises(ValueError, match="no tenant_id"):
        ArchiveService.archive_record("sales", rec)


def test_soft_delete(db_session, sample_customer):
    ArchiveService.soft_delete(sample_customer)
    assert sample_customer.is_active is False


def test_hard_delete_with_and_without_archive(db_session, sample_customer, sample_tenant):
    from models import ArchivedRecord

    with patch.object(ArchiveService, "archive_record",
                      return_value=SimpleNamespace(id=1)) as ar:
        ArchiveService.hard_delete("customers", sample_customer, archive_first=True)
        ar.assert_called_once()
    before = ArchivedRecord.query.count()
    ArchiveService.hard_delete("customers", sample_customer, archive_first=False)
    assert ArchivedRecord.query.count() == before


def test_hard_delete_failure_reraises():
    with patch.object(ArchiveService, "archive_record", side_effect=RuntimeError("x")), \
         pytest.raises(RuntimeError):
        ArchiveService.hard_delete("t", SimpleNamespace(id=1, tenant_id=1))


def test_restore_unknown_table_raises(db_session, sample_tenant):
    from models import ArchivedRecord

    rec = ArchivedRecord(tenant_id=sample_tenant.id, table_name="nope", record_id=1, data={})
    db_session.add(rec)
    db_session.flush()
    ArchiveService.ARCHIVE_MODEL_MAP["nope"] = None
    try:
        with pytest.raises(ValueError, match="Model not found"):
            ArchiveService.restore_record(rec)
    finally:
        ArchiveService.ARCHIVE_MODEL_MAP.pop("nope", None)


def test_restore_tenant_mismatch_raises(db_session, sample_tenant):
    from models import ArchivedRecord, Tenant

    # Create a different tenant for the archived record
    other_tenant = Tenant(
        name="Other Tenant",
        name_ar="مستأجر آخر",
        slug="other-tenant",
        email="other@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(other_tenant)
    db_session.flush()

    rec = ArchivedRecord(tenant_id=other_tenant.id, table_name="sales", record_id=1, data={})
    db_session.add(rec)
    db_session.flush()
    with patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id):
        with pytest.raises(PermissionError, match="tenant mismatch"):
            ArchiveService.restore_record(rec)


def test_restore_existing_reactivates(db_session, sample_customer):
    from models import ArchivedRecord

    sample_customer.is_active = False
    db_session.flush()
    rec = ArchivedRecord(tenant_id=sample_customer.tenant_id, table_name="customers",
                         record_id=sample_customer.id, data={})
    db_session.add(rec)
    db_session.flush()
    with patch.dict(ArchiveService.ARCHIVE_MODEL_MAP, {"customers": type(sample_customer)}), \
         patch("utils.tenanting.get_active_tenant_id", return_value=None):
        out = ArchiveService.restore_record(rec)
        assert out.is_active is True


def test_restore_missing_record_raises(db_session, sample_tenant):
    from models import ArchivedRecord, Customer

    rec = ArchivedRecord(tenant_id=sample_tenant.id, table_name="customers",
                         record_id=999999999, data={})
    db_session.add(rec)
    db_session.flush()
    with patch.dict(ArchiveService.ARCHIVE_MODEL_MAP, {"customers": Customer}), \
         patch("utils.tenanting.get_active_tenant_id", return_value=None):
        with pytest.raises(ValueError, match="not found in database"):
            ArchiveService.restore_record(rec)


def test_queries_and_cleanup(db_session, sample_tenant):
    from models import ArchivedRecord

    rec = ArchivedRecord(tenant_id=sample_tenant.id, table_name="sales", record_id=1, data={},
                         can_restore=False)
    db_session.add(rec)
    db_session.flush()
    assert ArchiveService.get_archived_records_query("sales").count() >= 1
    assert ArchiveService.get_archived_records_query().count() >= 1
    assert isinstance(ArchiveService.get_archived_records(limit=2), list)
    # old non-restorable archives get cleaned
    rec.archived_at = rec.archived_at.replace(year=2000)
    db_session.flush()
    assert ArchiveService.cleanup_old_archives(days=365) >= 1
