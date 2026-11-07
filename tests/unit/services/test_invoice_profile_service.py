"""The tenant profile is the source for document fields."""

from uuid import uuid4

from flask import g

from models import Tenant
from services.invoice_profile_service import get_company_print_context, resolve_print_profile


def test_profile_uses_selected_tenant_not_active_tenant(db_session, sample_tenant, app):
    other = Tenant(name=f"Other {uuid4()}", name_ar="Other", slug=f"other-{uuid4()}")
    db_session.add(other)
    db_session.flush()
    sample_tenant.bank_name = "Selected tenant bank"
    other.bank_name = "Active tenant bank"

    with app.test_request_context():
        g.active_tenant_id = other.id
        settings = resolve_print_profile(sample_tenant.id)

    assert settings.bank_name == "Selected tenant bank"
    assert settings.bank_name != other.bank_name


def test_context_returns_one_tenant_pinned_profile(db_session, sample_tenant, app):
    sample_tenant.bank_name = "Pinned bank"
    sample_tenant.tax_number = "PINNED-TAX"
    sample_tenant.name_ar = "شركة محددة"
    sample_tenant.name_en = "Pinned Company"

    with app.test_request_context():
        tenant, settings, company = get_company_print_context(tenant_id=sample_tenant.id)

    assert tenant.id == sample_tenant.id
    assert settings.tenant_id == sample_tenant.id
    assert company["name_ar"] == "شركة محددة"
    assert settings.bank_name == "Pinned bank"
    assert company["tax_number"] == settings.tax_number


def test_profile_snapshot_does_not_echo_another_tenant(db_session, sample_tenant):
    other = Tenant(name=f"Other {uuid4()}", name_ar="Other", slug=f"other-{uuid4()}")
    db_session.add(other)
    db_session.flush()
    sample_tenant.tax_number = "SELECTED-TAX"
    other.tax_number = "OTHER-TAX"

    assert resolve_print_profile(sample_tenant.id).tax_number == "SELECTED-TAX"
    assert resolve_print_profile(other.id).tax_number == "OTHER-TAX"
