"""AP aging report routes — HTML preview, JSON envelope, PDF download."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _report():
    return {
        "as_of": "2026-08-22",
        "rows": [
            {
                "supplier_id": 10,
                "supplier_name": "Supp X",
                "buckets": {"0-30": 100.0, "31-60": 0.0, "61-90": 250.0, "90+": 0.0},
                "total": 350.0,
                "open_purchases": 2,
                "invoices": [],
            }
        ],
        "totals": {"0-30": 100.0, "31-60": 0.0, "61-90": 250.0, "90+": 0.0, "total": 350.0},
        "supplier_count": 1,
        "generated_for_supplier": None,
    }


@pytest.fixture
def ap_aging_client(app_factory, bypass_reports_auth):
    from routes.reports import reports_bp

    app = app_factory(reports_bp)
    with patch("routes.reports.render_template", return_value="ok"):
        yield app.test_client()


class TestAPAgingPreview:
    def test_preview_returns_200(self, ap_aging_client):
        with patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()):
            resp = ap_aging_client.get("/reports/ap-aging")
        assert resp.status_code == 200

    def test_preview_forwards_filters(self, ap_aging_client):
        with patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()) as svc:
            ap_aging_client.get("/reports/ap-aging?as_of=2026-08-22&supplier=10")
        assert svc.call_args.kwargs["as_of_date"] == "2026-08-22"
        assert svc.call_args.kwargs["supplier_id"] == 10

    def test_preview_seller_gets_403(self, ap_aging_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        resp = ap_aging_client.get("/reports/ap-aging")
        assert resp.status_code == 403

    def test_unauthenticated_redirects(self, app_factory, bypass_reports_auth):
        from routes.reports import reports_bp
        from tests.unit.routes.conftest import unauthenticated_client

        app = app_factory(reports_bp)
        client = app.test_client()
        with unauthenticated_client(client):
            resp = client.get("/reports/ap-aging", follow_redirects=False)
        assert resp.status_code in (301, 302, 401)


class TestAPAgingJSON:
    def test_json_envelope_shape(self, ap_aging_client):
        with patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()):
            resp = ap_aging_client.get("/reports/api/ap-aging")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        body = resp.get_json()
        assert body["success"] is True
        assert body["errors"] is None
        data = body["data"]
        assert set(data) >= {"rows", "totals", "as_of", "supplier_count"}
        assert data["supplier_count"] == 1
        assert data["totals"]["total"] == pytest.approx(350.0)
        row = data["rows"][0]
        assert row["supplier_id"] == 10
        assert set(row["buckets"]) == {"0-30", "31-60", "61-90", "90+"}

    def test_json_forwards_filters(self, ap_aging_client):
        with patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()) as svc:
            ap_aging_client.get("/reports/api/ap-aging?as_of=2026-01-01&supplier=3")
        assert svc.call_args.kwargs["as_of_date"] == "2026-01-01"
        assert svc.call_args.kwargs["supplier_id"] == 3

    def test_json_seller_gets_403_envelope(self, ap_aging_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        resp = ap_aging_client.get("/reports/api/ap-aging")
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False


class TestAPAgingPDFExport:
    def test_pdf_download_content_type(self, ap_aging_client):
        with (
            patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()),
            patch("services.print_service.PrintService.render_pdf", return_value=b"%PDF-1.4 fake pdf bytes"),
        ):
            resp = ap_aging_client.get("/reports/ap-aging/export?format=pdf&as_of=2026-08-22")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.headers["Content-Disposition"].startswith("attachment")
        assert b"%PDF" in resp.data

    def test_pdf_default_format_is_pdf(self, ap_aging_client):
        with (
            patch("routes.reports.ReportsQueryService.build_ap_aging_report", return_value=_report()),
            patch("services.print_service.PrintService.render_pdf", return_value=b"%PDF-1.4 x") as render_pdf,
        ):
            resp = ap_aging_client.get("/reports/ap-aging/export")
        assert resp.status_code == 200
        assert render_pdf.call_args.args[0] == "reports/ap_aging_pdf.html"

    def test_pdf_unsupported_format_rejected(self, ap_aging_client):
        resp = ap_aging_client.get("/reports/ap-aging/export?format=csv")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_pdf_seller_gets_403(self, ap_aging_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        resp = ap_aging_client.get("/reports/ap-aging/export")
        assert resp.status_code == 403
