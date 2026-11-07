"""Tenant profile tax constants — creation/edit lock the statutory rate."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def to_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


def test_create_locks_rate_to_country(to_client):
    with (
        patch(
            "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
            return_value=[],
        ),
        patch(
            "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
            return_value=None,
        ),
        patch("routes.owner.tenants.Tenant") as tcls,
        patch("routes.owner.tenants.db.session"),
        patch("models.ensure_default_pos_order_types", return_value=None),
        patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
        patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
    ):
        tcls.return_value = MagicMock(id=11)
        resp = to_client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة",
                "slug": "co-tax",
                "default_currency": "ILS",
                "vat_country": "PS",
                "enable_tax": "on",
                "prices_include_vat": "on",
                "vat_number": "123456789",
                "logo_url": "https://x.example/logo.png",
            },
        )
        assert resp.status_code in (200, 302, 303)
        kwargs = tcls.call_args.kwargs
        assert kwargs["vat_country"] == "PS"
        assert kwargs["default_tax_rate"] == Decimal("16.00")
        assert kwargs["enable_tax"] is True
        assert kwargs["prices_include_vat"] is True
        assert kwargs["vat_number"] == "123456789"
        assert kwargs["logo_url"] == "https://x.example/logo.png"


def test_create_rejects_invalid_trn(to_client):
    with (
        patch(
            "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
            return_value=[],
        ),
        patch(
            "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
            return_value=None,
        ),
        patch("routes.owner.tenants.Tenant") as tcls,
    ):
        resp = to_client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة",
                "slug": "co-badtrn",
                "default_currency": "ILS",
                "vat_country": "PS",
                "vat_number": "12",
            },
        )
        assert resp.status_code in (200, 302, 303)
        # An invalid tax number must never create the tenant.
        tcls.assert_not_called()


def test_edit_relocks_rate_on_country_change(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.default_tax_rate = Decimal("5.00")
    tenant.enable_tax = True
    tenant.vat_number = "123456789012345"
    tenant.tax_number = ""
    tenant.logo_url = ""
    tenant.prices_include_vat = False
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
        patch("routes.owner.tenants.render_template", return_value="form"),
    ):
        resp = to_client.post(
            f"/owner/tenants/{tenant.id}/edit",
            data={
                "name_ar": "أكمي",
                "name_en": "Acme",
                "slug": "acme",
                "default_currency": "ILS",
                "vat_country": "PS",
                "enable_tax": "on",
                "vat_number": "123456789",
                "tax_number": "",
                "logo_url": "https://x.example/logo.png",
            },
        )
        assert resp.status_code in (200, 302, 303)
        assert tenant.vat_country == "PS"
        assert tenant.default_tax_rate == Decimal("16.00")
        assert tenant.enable_tax is True
        assert tenant.logo_url == "https://x.example/logo.png"
