import io
from unittest.mock import MagicMock, patch

import pytest
from flask import make_response

from tests.unit.routes.conftest import (
    unauthenticated_client,
)


@pytest.fixture
def treasury_client(app_factory, bypass_permission_auth):
    from routes.treasury import treasury_bp

    app = app_factory(treasury_bp)
    return app.test_client()


def _treasury_report():
    return {
        "liquidity": {
            "accounts": [
                {
                    "kind_label": "Cash",
                    "code": "1000",
                    "name": "Main Cash",
                    "currency": "AED",
                    "balance_aed": 5000,
                    "source": "gl",
                }
            ]
        }
    }


def _export_io():
    return io.BytesIO(b"export-bytes")


def _send_file_response():
    return make_response("file", 200, {"Content-Type": "application/octet-stream"})


def _base_treasury_patches(report=None, branches=None):
    report = report if report is not None else _treasury_report()
    branches = branches if branches is not None else [MagicMock(id=1, name="Main")]
    return {
        "build_dashboard": patch(
            "services.treasury_service.TreasuryService.build_dashboard",
            return_value=report,
        ),
        "branches": patch(
            "routes.treasury.get_accessible_branches",
            return_value=branches,
        ),
        "render": patch("routes.treasury.render_template", return_value="ok"),
        "scope": patch("routes.treasury.report_branch_scope_id", return_value=None),
        "access": patch("routes.treasury.user_can_access_branch", return_value=True),
    }


class TestTreasuryDashboard:
    def test_treasury_returns_200(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patches["branches"],
            patches["render"] as render,
            patches["scope"],
            patches["access"],
        ):
            resp = treasury_client.get("/reports/treasury")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "reports/treasury.html"

    def test_treasury_with_branch_id_arg(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"] as build,
            patches["branches"],
            patches["render"],
            patches["scope"],
            patches["access"],
        ):
            resp = treasury_client.get("/reports/treasury?branch_id=3")
        assert resp.status_code == 200
        build.assert_called_once_with(tenant_id=1, branch_id=3)

    def test_treasury_branch_scope_mismatch_403(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patches["branches"],
            patch("routes.treasury.report_branch_scope_id", return_value=2),
            patches["render"] as render,
            patches["access"],
        ):
            resp = treasury_client.get("/reports/treasury?branch_id=5")
        assert resp.status_code == 403
        render.assert_called_once_with("errors/403.html")

    def test_treasury_branch_not_accessible_403(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patches["branches"],
            patches["scope"],
            patch("routes.treasury.user_can_access_branch", return_value=False),
            patches["render"] as render,
        ):
            resp = treasury_client.get("/reports/treasury?branch_id=9")
        assert resp.status_code == 403
        render.assert_called_once_with("errors/403.html")

    def test_treasury_unauthenticated_401(self, treasury_client):
        with unauthenticated_client(treasury_client):
            resp = treasury_client.get("/reports/treasury")
        assert resp.status_code == 401

    def test_treasury_no_permission_403(self, treasury_client, mock_user):
        mock_user.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = treasury_client.get("/reports/treasury")
        assert resp.status_code == 403


class TestTreasuryExport:
    def test_export_xlsx_default(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patches["scope"],
            patches["access"],
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ) as xlsx,
            patch(
                "routes.treasury.send_file", return_value=_send_file_response()
            ) as send_file,
        ):
            resp = treasury_client.get("/reports/treasury/export")
        assert resp.status_code == 200
        xlsx.assert_called_once()
        send_file.assert_called_once()

    def test_export_csv_explicit(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patches["scope"],
            patches["access"],
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=_export_io(),
            ) as csv,
            patch("routes.treasury.send_file", return_value=_send_file_response()),
        ):
            resp = treasury_client.get("/reports/treasury/export?format=csv")
        assert resp.status_code == 200
        csv.assert_called_once()

    def test_export_branch_scope_mismatch_403(self, treasury_client):
        patches = _base_treasury_patches()
        with (
            patches["build_dashboard"],
            patch("routes.treasury.report_branch_scope_id", return_value=1),
            patches["access"],
            patches["render"] as render,
        ):
            resp = treasury_client.get("/reports/treasury/export?branch_id=2")
        assert resp.status_code == 403
        render.assert_called_once_with("errors/403.html")

    def test_export_unauthenticated_401(self, treasury_client):
        with unauthenticated_client(treasury_client):
            resp = treasury_client.get("/reports/treasury/export")
        assert resp.status_code == 401


class TestTreasuryVatReturn:
    def test_vat_return_returns_200(self, treasury_client):
        report = {"total_vat": 100}
        with (
            patch(
                "services.tax_service.TaxService.get_vat_return", return_value=report
            ) as tax,
            patch("routes.treasury.render_template", return_value="vat") as render,
        ):
            resp = treasury_client.get(
                "/reports/vat-return",
                query_string={"date_from": "2025-01-01", "date_to": "2025-03-31"},
            )
        assert resp.status_code == 200
        tax.assert_called_once_with("2025-01-01", "2025-03-31", 1)
        render.assert_called_once_with("reports/vat_return.html", report=report)

    def test_vat_return_unauthenticated_401(self, treasury_client):
        with unauthenticated_client(treasury_client):
            resp = treasury_client.get("/reports/vat-return")
        assert resp.status_code == 401


class TestTreasuryWpsExport:
    def test_wps_export_success(self, treasury_client):
        strategy = MagicMock()
        strategy.supports_wps = True
        strategy.get_wps_format.return_value = {"lines": ["HDR", "ROW1"]}
        tenant = MagicMock()
        tenant.vat_country = "AE"
        with (
            patch("utils.localization.get_strategy", return_value=strategy),
            patch("routes.treasury.db.session") as mock_session,
            patch("routes.treasury.render_template"),
        ):
            mock_session.get.return_value = tenant
            resp = treasury_client.get("/reports/wps-export")
        assert resp.status_code == 200
        assert resp.mimetype.startswith("text/plain")
        assert b"HDR" in resp.data

    def test_wps_export_not_supported_403(self, treasury_client):
        strategy = MagicMock()
        strategy.supports_wps = False
        tenant = MagicMock()
        tenant.vat_country = "US"
        with (
            patch("utils.localization.get_strategy", return_value=strategy),
            patch("routes.treasury.db.session") as mock_session,
            patch(
                "routes.treasury.render_template", return_value="forbidden"
            ) as render,
        ):
            mock_session.get.return_value = tenant
            resp = treasury_client.get("/reports/wps-export")
        assert resp.status_code == 403
        render.assert_called_once()
        assert "WPS" in render.call_args[1]["message"]

    def test_wps_export_unauthenticated_401(self, treasury_client):
        with unauthenticated_client(treasury_client):
            resp = treasury_client.get("/reports/wps-export")
        assert resp.status_code == 401
