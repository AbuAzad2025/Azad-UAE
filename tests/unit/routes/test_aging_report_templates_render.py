"""Real end-to-end rendering of the aging / AP-aging report templates.

These tests exist to actually RENDER three templates through their routes so
the template-coverage tracker (templates_rendered.json) counts them:

  - templates/ledger/aging_analysis_pdf.html  (via /ledger/aging-analysis/export)
  - templates/reports/ap_aging.html           (via /reports/ap-aging)
  - templates/reports/ap_aging_pdf.html       (via /reports/ap-aging/export)

Unlike the older suites (test_ledger_routes.py, test_reports_ap_aging.py)
which mock ``render_template`` / ``PrintService.render_pdf``, these tests go
through the full app with a logged-in user and seeded supplier/customer rows,
and let WeasyPrint produce REAL PDF bytes.
"""

from __future__ import annotations

import re
import zlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

AS_OF = "2026-08-01"
_SUPPLIER_MARKER = "AgingRenderSupplier"
_CUSTOMER_MARKER = "AgingRenderCustomer"


def _pdf_page_objects(pdf_bytes):
    """Concatenated decompressed body of every FlateDecode stream in a PDF.

    WeasyPrint packs page dictionaries into compressed object streams, so
    ``/Type /Page`` is only visible after inflating them.
    """
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            continue
    return b"\n".join(chunks)


def _assert_real_pdf(pdf_bytes):
    assert pdf_bytes.startswith(b"%PDF")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
    assert b"/Filter /FlateDecode" in pdf_bytes
    assert b"/Type /Page" in _pdf_page_objects(pdf_bytes)
    assert len(pdf_bytes) > 1000


def _as_of_date():
    return datetime.strptime(AS_OF, "%Y-%m-%d").date()


def _aware(days_offset):
    """Datetime AS_OF + offset days, tz-aware like the models' defaults."""
    return datetime.combine(_as_of_date(), datetime.min.time(), tzinfo=UTC) + timedelta(days=days_offset)


def _grant_report_permissions(db_session, user):
    from models import Permission

    role = user.role
    for code in ("view_ledger", "view_reports"):
        if not any(p.code == code for p in role.permissions):
            perm = db_session.query(Permission).filter_by(code=code).first()
            if perm is None:
                perm = Permission(code=code, name=code, name_ar=code, category="test")
                db_session.add(perm)
            role.permissions.append(perm)
    db_session.commit()


def _login(client, user):
    resp = client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


@pytest.fixture
def aging_client(client, db_session, sample_user):
    _grant_report_permissions(db_session, sample_user)
    _login(client, sample_user)
    return client


@pytest.fixture
def seeded_supplier_with_purchases(db_session, sample_tenant, sample_user):
    """One active supplier + confirmed purchases landing in different buckets."""
    from models import Purchase, Supplier

    supplier = Supplier(
        tenant_id=sample_tenant.id,
        name=_SUPPLIER_MARKER,
        email="aging-render@test.com",
        phone="0555000123",
        is_active=True,
    )
    db_session.add(supplier)
    db_session.commit()

    specs = [  # (days before as_of, amount) → bucket coverage: 0-30 / 61-90 / 90+
        (-20, Decimal("300.000")),
        (-75, Decimal("500.000")),
        (-130, Decimal("120.000")),
    ]
    for idx, (offset, total) in enumerate(specs, start=1):
        db_session.add(
            Purchase(
                tenant_id=sample_tenant.id,
                purchase_number=f"PUR-AGINGRENDER-{idx}",
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                purchase_date=_aware(offset),
                user_id=sample_user.id,
                subtotal=total,
                total_amount=total,
                amount=total,
                amount_aed=total,
                currency="AED",
                status="confirmed",
            )
        )
    db_session.commit()
    return supplier


class TestAPAgingTemplates:
    def test_ap_aging_html_renders_seeded_supplier(self, aging_client, seeded_supplier_with_purchases):
        resp = aging_client.get(f"/reports/ap-aging?as_of={AS_OF}")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        body = resp.get_data(as_text=True)
        assert _SUPPLIER_MARKER in body
        assert ">0-30</th>" in body
        assert ">31-60</th>" in body

    def test_ap_aging_pdf_export_is_real_pdf(self, aging_client, seeded_supplier_with_purchases):
        resp = aging_client.get(f"/reports/ap-aging/export?format=pdf&as_of={AS_OF}")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.headers["Content-Disposition"] == f"attachment; filename=ap_aging_{AS_OF.replace('-', '')}.pdf"
        _assert_real_pdf(resp.get_data())

    def test_ap_aging_print_template_shows_seeded_buckets(self, app, db_session, seeded_supplier_with_purchases):
        """The print template must carry the seeded supplier + bucket split through the real service."""
        from services.print_service import PrintService
        from services.reports_query_service import ReportsQueryService

        tenant_id = seeded_supplier_with_purchases.tenant_id
        report = ReportsQueryService.build_ap_aging_report(tenant_id, None, as_of_date=AS_OF)
        with app.app_context():
            html = PrintService.render_print(
                "reports/ap_aging_pdf.html",
                {"title": "AP Aging", "report": report, "as_of": AS_OF, "selected_branch": None},
            )
        assert _SUPPLIER_MARKER in html
        row = next(r for r in report["rows"] if r["supplier_name"] == _SUPPLIER_MARKER)
        buckets = row["buckets"]
        # 300 @ -20d → 0-30 ; 500 @ -75d → 61-90 ; 120 @ -130d → 90+
        assert buckets["0-30"] == pytest.approx(300.0)
        assert buckets["61-90"] == pytest.approx(500.0)
        assert buckets["90+"] == pytest.approx(120.0)


class TestLedgerAgingPdfTemplate:
    def test_payables_pdf_export_is_real_pdf(self, aging_client, seeded_supplier_with_purchases):
        resp = aging_client.get(f"/ledger/aging-analysis/export?type=payables&as_of_date={AS_OF}")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert "filename=aging_analysis_payables_" in resp.headers["Content-Disposition"]
        _assert_real_pdf(resp.get_data())

    def test_receivables_pdf_export_is_real_pdf(self, aging_client, db_session, sample_tenant, sample_user):
        from models import Customer, Sale

        customer = Customer(
            tenant_id=sample_tenant.id,
            name=_CUSTOMER_MARKER,
            email="aging-render-cust@test.com",
            phone="0555000456",
            is_active=True,
        )
        db_session.add(customer)
        db_session.commit()

        db_session.add(
            Sale(
                tenant_id=sample_tenant.id,
                customer_id=customer.id,
                sale_number="S-AGINGRENDER-1",
                sale_date=_aware(-100),
                seller_id=sample_user.id,
                subtotal=Decimal("800.000"),
                total_amount=Decimal("800.000"),
                amount=Decimal("800.000"),
                amount_aed=Decimal("800.000"),
                paid_amount=Decimal("0"),
                paid_amount_aed=Decimal("0"),
                balance_due=Decimal("800.000"),
                currency="AED",
                exchange_rate=1,
                payment_status="unpaid",
                status="confirmed",
                source="internal",
                notes="",
            )
        )
        db_session.commit()

        resp = aging_client.get(f"/ledger/aging-analysis/export?type=receivables&as_of_date={AS_OF}")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert "filename=aging_analysis_receivables_" in resp.headers["Content-Disposition"]
        _assert_real_pdf(resp.get_data())
