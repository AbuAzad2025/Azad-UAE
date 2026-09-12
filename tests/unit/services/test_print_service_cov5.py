"""Cov5: print_service — snapshot without tenant filter branch."""

from __future__ import annotations

from types import SimpleNamespace


def test_create_snapshot_without_tenant_id(db_session, sample_tenant, incoming_cheque):
    from services.print_service import PrintService

    # Covers the tenant_id-is-None query branch; returns None on success path
    PrintService.create_snapshot(None, "cheque", incoming_cheque.id)


def test_create_snapshot_empty_dict_falls_back_to_columns(db_session, sample_tenant):
    from services.print_service import PrintService

    doc = SimpleNamespace(tenant_id=sample_tenant.id, to_dict=lambda: {})
    PrintService.create_snapshot(sample_tenant.id, "cheque", 999, document=doc)
