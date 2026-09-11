"""Coverage for routes/treasury.py remaining arcs.

Targets: branch-mismatch 403 arcs (dashboard + export), export csv arc,
wps missing-tenant / unsupported-country / no-payroll arcs, vat arc.
Real test-client paths; service boundaries mocked only.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def treasury_cov3_client(app_factory, bypass_permission_auth):
    from routes.treasury import treasury_bp

    app = app_factory(treasury_bp)
    return app.test_client()


def _report():
    return {
        "liquidity": {
            "accounts": [
                {
                    "kind_label": "Cash",
                    "code": "1000",
                    "name": "Main",
                    "currency": "AED",
                    "balance_aed": 100,
                    "source": "gl",
                }
            ]
        }
    }


class TestTreasuryGuards:
    def test_dashboard_branch_mismatch_403(self, treasury_cov3_client):
        with (
            patch("routes.treasury.report_branch_scope_id", return_value=1),
            patch("routes.treasury.render_template", return_value="denied"),
        ):
            resp = treasury_cov3_client.get("/reports/treasury?branch_id=2")
        assert resp.status_code == 403

    def test_export_branch_mismatch_403(self, treasury_cov3_client):
        with (
            patch("routes.treasury.report_branch_scope_id", return_value=1),
            patch("routes.treasury.render_template", return_value="denied"),
        ):
            resp = treasury_cov3_client.get("/reports/treasury/export?branch_id=2")
        assert resp.status_code == 403

    def test_export_csv(self, treasury_cov3_client):
        with (
            patch("routes.treasury.report_branch_scope_id", return_value=None),
            patch(
                "services.treasury_service.TreasuryService.build_dashboard",
                return_value=_report(),
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=io.BytesIO(b"csv"),
            ),
            patch("routes.treasury.get_accessible_branches", return_value=[]),
        ):
            resp = treasury_cov3_client.get("/reports/treasury/export?format=csv")
        assert resp.status_code == 200

    def test_vat_return(self, treasury_cov3_client):
        with (
            patch("services.tax_service.TaxService.get_vat_return", return_value={"total": 0}),
            patch("routes.treasury.render_template", return_value="ok"),
        ):
            resp = treasury_cov3_client.get("/reports/vat-return?date_from=2026-01-01")
        assert resp.status_code == 200


class TestWps:
    def test_missing_tenant_redirects(self, treasury_cov3_client):
        with patch("routes.treasury.get_active_tenant_id", return_value=None):
            resp = treasury_cov3_client.get("/reports/wps-export")
        assert resp.status_code == 302

    def test_unsupported_country_403(self, treasury_cov3_client):
        tenant = MagicMock(vat_country="US")
        strategy = MagicMock(supports_wps=False)
        with (
            patch("routes.treasury.get_active_tenant_id", return_value=1),
            patch("routes.treasury.db.session.get", return_value=tenant),
            patch("utils.localization.get_strategy", return_value=strategy),
            patch("routes.treasury.render_template", return_value="denied"),
        ):
            resp = treasury_cov3_client.get("/reports/wps-export")
        assert resp.status_code == 403

    def test_no_payroll_redirects(self, treasury_cov3_client):
        tenant = MagicMock(vat_country="AE")
        strategy = MagicMock(supports_wps=True)
        with (
            patch("routes.treasury.get_active_tenant_id", return_value=1),
            patch("routes.treasury.db.session.get", return_value=tenant),
            patch("utils.localization.get_strategy", return_value=strategy),
            patch("services.payroll_service.PayrollService.get_wps_rows", return_value=[]),
        ):
            resp = treasury_cov3_client.get("/reports/wps-export?month=1&year=2026")
        assert resp.status_code == 302

    def test_wps_success(self, treasury_cov3_client):
        tenant = MagicMock(vat_country="AE")
        strategy = MagicMock(supports_wps=True)
        strategy.get_wps_format.return_value = {"content": "a,b,c", "lines": ["a,b,c"]}
        with (
            patch("routes.treasury.get_active_tenant_id", return_value=1),
            patch("routes.treasury.db.session.get", return_value=tenant),
            patch("utils.localization.get_strategy", return_value=strategy),
            patch(
                "services.payroll_service.PayrollService.get_wps_rows",
                return_value=[{"name": "Emp"}],
            ),
        ):
            resp = treasury_cov3_client.get("/reports/wps-export?month=2&year=2026")
        assert resp.status_code == 200
        assert b"a,b,c" in resp.data
