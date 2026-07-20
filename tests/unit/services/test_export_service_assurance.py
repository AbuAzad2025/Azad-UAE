"""Export service — CSV/XLSX streams, PDF HTML, domain exporters."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock


class TestCsvExport:
    """export_to_csv — BOM stream for Excel, row iteration."""

    def test_csv_stream_has_utf8_bom_and_headers(self):
        from services.export_service import ExportService

        buf = ExportService.export_to_csv(
            [["1", "Alice"], ["2", "Bob"]],
            ["ID", "Name"],
        )
        assert isinstance(buf, BytesIO)
        raw = buf.getvalue()
        assert raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        assert "ID,Name" in text
        assert "Alice" in text

    def test_empty_data_still_writes_headers(self):
        from services.export_service import ExportService

        buf = ExportService.export_to_csv([], ["A", "B"])
        text = buf.getvalue().decode("utf-8-sig")
        assert text.strip() == "A,B"


class TestXlsxExport:
    """export_to_xlsx — sheet naming, column width cap (memory guard)."""

    def test_xlsx_workbook_stream(self):
        from services.export_service import ExportService

        long_val = "x" * 100
        buf = ExportService.export_to_xlsx(
            [["1", long_val]],
            ["ID", "Value"],
            sheet_name="LedgerExport",
        )
        assert isinstance(buf, BytesIO)
        assert buf.getvalue()[:2] == b"PK"

    def test_sheet_name_truncated_to_31_chars(self):
        from openpyxl import load_workbook
        from services.export_service import ExportService

        buf = ExportService.export_to_xlsx(
            [["a"]],
            ["H"],
            sheet_name="A" * 40,
        )
        wb = load_workbook(buf)
        assert len(wb.active.title) <= 31


class TestPdfReport:
    """generate_pdf_report — HTML stream with stats and table blocks."""

    def test_pdf_html_includes_title_and_stats(self):
        from services.export_service import ExportService

        html = ExportService.generate_pdf_report(
            "تقرير المبيعات",
            {
                "stats": {"إجمالي": "5000"},
                "table_headers": ["رقم", "مبلغ"],
                "table_data": [["1", "100"]],
            },
        )
        assert "تقرير المبيعات" in html
        assert "5000" in html
        assert "<table>" in html

    def test_empty_table_omits_table_block(self):
        from services.export_service import ExportService

        html = ExportService.generate_pdf_report("Empty", {"stats": {}, "table_data": [], "table_headers": []})
        assert "<table>" not in html


class TestDomainExports:
    """export_purchases/donations/cards_to_csv — chunked row materialization."""

    def test_purchases_export_rows(self):
        pkg = MagicMock()
        pkg.name_ar = "باقة ذهبية"
        purchase = MagicMock(
            id=1,
            package=pkg,
            customer_name="Ali",
            customer_email="a@x.com",
            amount_paid=99.0,
            payment_method="card",
            payment_status="completed",
            created_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        from services.export_service import ExportService

        buf = ExportService.export_purchases_to_csv([purchase])
        text = buf.getvalue().decode("utf-8-sig")
        assert "Ali" in text
        assert "99" in text

    def test_donations_anonymous_fallback(self):
        donation = MagicMock(
            id=2,
            donor_name=None,
            donor_email=None,
            amount_usd=25,
            payment_method="paypal",
            status="completed",
            created_at=None,
        )
        from services.export_service import ExportService

        buf = ExportService.export_donations_to_csv([donation])
        text = buf.getvalue().decode("utf-8-sig")
        assert "مجهول" in text

    def test_cards_export_uses_display_helper(self):
        card = MagicMock(
            id=3,
            customer_name="Sara",
            customer_email="s@x.com",
            card_type="visa",
            amount=50,
            status="active",
            created_at=datetime(2025, 1, 1),
        )
        card.get_card_display.return_value = "****4242"
        from services.export_service import ExportService

        buf = ExportService.export_cards_to_csv([card])
        text = buf.getvalue().decode("utf-8-sig")
        assert "****4242" in text

    def test_large_ledger_chunk_processing(self):
        """Many rows stream through export_to_csv without loading entire workbook."""
        from services.export_service import ExportService

        rows = [[i, f"row-{i}", i * 10.5] for i in range(5000)]
        buf = ExportService.export_to_csv(rows, ["ID", "Label", "Amount"])
        lines = buf.getvalue().decode("utf-8-sig").strip().splitlines()
        assert len(lines) == 5001
