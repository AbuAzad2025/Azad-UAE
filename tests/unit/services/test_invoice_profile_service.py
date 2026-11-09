"""Unit tests for the unified invoice profile plumbing."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from flask import g

from models import Tenant
from services.invoice_profile_service import (
    build_invoice_settings_snapshot_from_id,
    get_company_print_context,
    resolve_print_profile,
)


class TestResolvePrintProfile:
    def test_none_tenant(self):
        assert resolve_print_profile(None) is None

    def test_snapshot_from_id_missing_tenant(self, mocker):
        mocker.patch("services.invoice_profile_service.db.session.get", return_value=None)
        assert build_invoice_settings_snapshot_from_id(1) is None

    def test_snapshot_from_id_found(self, mocker):
        tenant = MagicMock()
        mocker.patch("services.invoice_profile_service.db.session.get", return_value=tenant)
        settings = MagicMock(company_name_ar="Co")
        builder = mocker.patch(
            "services.invoice_profile_service.build_invoice_settings_snapshot", return_value=settings
        )
        assert build_invoice_settings_snapshot_from_id(1) is settings
        builder.assert_called_once_with(tenant)


class TestCompanyContext:
    def test_no_ids_at_all(self):
        tenant, settings, company = get_company_print_context()
        assert tenant is settings is company is None

    def test_user_tenant_missing(self, mocker):
        mocker.patch(
            "services.invoice_profile_service.db.session.get",
            return_value=None,
        )
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        tenant, _, company = get_company_print_context(user=MagicMock())
        assert tenant is None and company is None


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
