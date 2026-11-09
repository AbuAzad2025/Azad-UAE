"""Unit tests for the unified invoice profile plumbing."""

from __future__ import annotations

from unittest.mock import MagicMock

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
