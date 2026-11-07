"""Tenant-scoped synchronization of existing invoice settings."""

from uuid import uuid4

import pytest
from flask import g

from models import Tenant
from models.invoice_settings import InvoiceSettings
from services.invoice_profile_service import InvoiceProfileConflict, InvoiceProfileService


def test_sync_updates_only_selected_fields_and_tenant(db_session, sample_tenant):
    other = Tenant(name=f"Other {uuid4()}", name_ar="Other", slug=f"other-{uuid4()}")
    db_session.add(other)
    db_session.flush()
    own = InvoiceSettings(
        tenant_id=sample_tenant.id,
        company_name_ar="Old",
        company_name_en="Old",
        bank_name="Own bank",
        footer_text_ar="Old footer",
        is_active=True,
    )
    theirs = InvoiceSettings(
        tenant_id=other.id,
        company_name_ar="Other",
        company_name_en="Other",
        bank_name="Other bank",
        footer_text_ar="Other footer",
        is_active=True,
    )
    db_session.add_all([own, theirs])
    db_session.flush()

    sample_tenant.footer_invoice_text_ar = "New footer"
    sample_tenant.bank_name = "Not submitted"
    InvoiceProfileService.sync_from_tenant(sample_tenant, {"footer_invoice_text_ar"})

    db_session.refresh(own)
    db_session.refresh(theirs)
    assert own.footer_text_ar == "New footer"
    assert own.bank_name == "Own bank"
    assert theirs.bank_name == "Other bank"
    assert theirs.footer_text_ar == "Other footer"


def test_sync_refuses_multiple_active_settings(db_session, sample_tenant):
    rows = [
        InvoiceSettings(
            tenant_id=sample_tenant.id,
            company_name_ar="Test",
            company_name_en="Test",
            bank_name=name,
            is_active=True,
        )
        for name in ("First", "Second")
    ]
    db_session.add_all(rows)
    db_session.flush()
    sample_tenant.bank_name = "New"

    with pytest.raises(InvoiceProfileConflict):
        InvoiceProfileService.sync_from_tenant(sample_tenant, {"bank_name"})

    assert [row.bank_name for row in rows] == ["First", "Second"]


def test_sync_does_not_create_a_settings_row(db_session, sample_tenant):
    sample_tenant.bank_name = "New"
    InvoiceProfileService.sync_from_tenant(sample_tenant, {"bank_name"})
    assert InvoiceSettings.query.filter_by(tenant_id=sample_tenant.id, is_active=True).count() == 0


def test_sync_optional_english_name_respects_print_column_constraint(db_session, sample_tenant):
    settings = InvoiceSettings(
        tenant_id=sample_tenant.id, company_name_ar="Test", company_name_en="Old", is_active=True
    )
    db_session.add(settings)
    db_session.flush()
    sample_tenant.name_en = None

    InvoiceProfileService.sync_from_tenant(sample_tenant, {"name_en"})

    db_session.refresh(settings)
    assert settings.company_name_en == sample_tenant.name


def test_owner_can_update_selected_tenant_when_another_is_active(app, db_session, sample_tenant):
    own = InvoiceSettings(
        tenant_id=sample_tenant.id,
        company_name_ar="Test",
        company_name_en="Test",
        bank_name="Old",
        is_active=True,
    )
    other = Tenant(name=f"Other {uuid4()}", name_ar="Other", slug=f"other-{uuid4()}")
    db_session.add_all([own, other])
    db_session.flush()
    other_id = other.id
    sample_tenant.bank_name = "Selected tenant bank"

    with app.test_request_context():
        g.active_tenant_id = other_id
        InvoiceProfileService.sync_from_tenant(sample_tenant, {"bank_name"})

    db_session.refresh(own)
    assert own.bank_name == "Selected tenant bank"
