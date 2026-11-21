"""Coverage gaps for services/ocr_service.py.

The optional OCR clients (pytesseract, PyMuPDF) are not installed in CI, so the
service's import guard leaves OCR disabled and nearly every branch is dead in
the combined coverage report. These tests mock the OCR clients at the service
boundary and drive the pure parsing logic directly. No production code is
changed.
"""

import builtins
import importlib
import io
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage

import services.ocr_service as ocr


def _png_bytes(mode="RGB", size=(20, 10)):
    buffer = io.BytesIO()
    PILImage.new(mode, size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


class TestOptionalImportGuard:
    def test_reload_with_pytesseract_present_executes_success_path(self):
        original = ocr.TESSERACT_AVAILABLE
        try:
            with patch.dict(sys.modules, {"pytesseract": MagicMock()}):
                reloaded = importlib.reload(ocr)
                assert reloaded.TESSERACT_AVAILABLE is True
                assert reloaded.OCRService.is_available() is True
        finally:
            # Restore the module to the state the real environment dictates.
            importlib.reload(ocr)
        assert ocr.TESSERACT_AVAILABLE is original


class TestConstructionAndAvailability:
    def test_default_construction(self):
        svc = ocr.OCRService()
        assert svc.lang == "ara+eng"
        assert svc._tesseract_path == "tesseract"

    def test_explicit_lang_and_tesseract_cmd(self):
        with patch.dict(ocr.os.environ, {"TESSERACT_CMD": "/opt/bin/tesseract"}):
            svc = ocr.OCRService(lang="eng")
        assert svc.lang == "eng"
        assert svc._tesseract_path == "/opt/bin/tesseract"

    def test_is_available_follows_module_flag(self):
        with patch.object(ocr, "TESSERACT_AVAILABLE", True):
            assert ocr.OCRService.is_available() is True
        with patch.object(ocr, "TESSERACT_AVAILABLE", False):
            assert ocr.OCRService.is_available() is False


class TestExtractTextFromImage:
    def test_disabled_ocr_raises(self):
        svc = ocr.OCRService()
        with patch.object(ocr, "TESSERACT_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="Tesseract OCR not available"):
                svc.extract_text_from_image(b"ignored")

    def test_success_preprocesses_image_and_calls_tesseract(self):
        svc = ocr.OCRService(lang="eng")
        tesseract = MagicMock()
        tesseract.image_to_string.return_value = "  recognised text  "
        with (
            patch.object(ocr, "TESSERACT_AVAILABLE", True),
            patch.object(ocr, "Image", PILImage, create=True),
            patch.object(ocr, "pytesseract", tesseract, create=True),
        ):
            result = svc.extract_text_from_image(_png_bytes())
        assert result == "  recognised text  "
        args, kwargs = tesseract.image_to_string.call_args
        assert kwargs["lang"] == "eng"
        assert kwargs["config"] == "--psm 6"
        assert args[0].mode == "L"
        assert args[0].width >= 1000

    def test_tesseract_exception_is_propagated(self):
        svc = ocr.OCRService()
        tesseract = MagicMock()
        tesseract.image_to_string.side_effect = RuntimeError("tesseract crashed")
        with (
            patch.object(ocr, "TESSERACT_AVAILABLE", True),
            patch.object(ocr, "Image", PILImage, create=True),
            patch.object(ocr, "pytesseract", tesseract, create=True),
        ):
            with pytest.raises(RuntimeError, match="tesseract crashed"):
                svc.extract_text_from_image(_png_bytes())


class TestPreprocessImage:
    def test_rgb_image_is_converted_and_upscaled(self):
        svc = ocr.OCRService()
        result = svc._preprocess_image(PILImage.new("RGB", (20, 10), "white"))
        assert result.mode == "L"
        assert result.size == (1000, 500)

    def test_large_grayscale_image_skips_conversion_and_resize(self):
        svc = ocr.OCRService()
        image = PILImage.new("L", (1200, 10), 255)
        result = svc._preprocess_image(image)
        assert result.mode == "L"
        assert result.size == (1200, 10)

    def test_old_pil_without_resampling_falls_back(self):
        svc = ocr.OCRService()
        real_import = builtins.__import__

        def _no_resampling(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "PIL.Image" and "Resampling" in (fromlist or ()):
                raise ImportError("old PIL")
            return real_import(name, globals, locals, fromlist, level)

        with (
            patch("builtins.__import__", side_effect=_no_resampling),
            patch.object(ocr, "Image", PILImage, create=True),
        ):
            result = svc._preprocess_image(PILImage.new("L", (10, 10), 255))
        assert result.size == (1000, 1000)


class TestExtractTextFromPdf:
    def test_missing_pymupdf_returns_empty_list(self):
        svc = ocr.OCRService()
        with patch.dict(sys.modules, {"fitz": None}):
            assert svc.extract_text_from_pdf(b"pdf") == []

    def test_each_page_is_rendered_and_ocrd(self):
        pix = MagicMock()
        pix.tobytes.return_value = b"png-bytes"
        page = MagicMock()
        page.get_pixmap.return_value = pix
        doc = MagicMock()
        doc.__len__.return_value = 2
        doc.__getitem__.return_value = page
        fitz = MagicMock()
        fitz.open.return_value = doc
        svc = ocr.OCRService()
        with (
            patch.dict(sys.modules, {"fitz": fitz}),
            patch.object(svc, "extract_text_from_image", side_effect=["page one", "page two"]) as extract,
        ):
            result = svc.extract_text_from_pdf(b"pdf bytes")
        assert result == ["page one", "page two"]
        fitz.open.assert_called_once_with(stream=b"pdf bytes", filetype="pdf")
        page.get_pixmap.assert_called_with(dpi=300)
        pix.tobytes.assert_called_with("png")
        assert extract.call_args_list[0].args == (b"png-bytes",)
        assert extract.call_count == 2
        doc.close.assert_called_once()


class TestExtractProductsFromText:
    def test_multiline_fields_and_table_rows(self):
        svc = ocr.OCRService()
        text = "\n".join(
            [
                "",
                "just noise",
                "Product Name: Widget A",
                "SKU: AB-123",
                "barcode: 12345678",
                "price: 10.5",
                "cost: 4.5",
                "category: Tools",
                "Qty: 2",
                "2 20.00",
                "Item: Gadget B",
                "sku: XY-9",
                "السعر: 5",
                "الكمية: 3",
                "3 15.00",
                "Product Name: Trailing item",
                "sku: ZZ-1",
                "price: 7",
            ]
        )
        assert svc.extract_products_from_text(text) == [
            {
                "name": "Widget A",
                "sku": "AB-123",
                "barcode": "12345678",
                "price": "10.5",
                "cost": "4.5",
                "category": "Tools",
                "quantity": "2",
            },
            {"name": "Gadget B", "sku": "XY-9", "price": "5", "quantity": "3"},
            {"name": "Trailing item", "sku": "ZZ-1", "price": "7"},
        ]

    def test_row_without_a_name_is_discarded_and_blanks_are_skipped(self):
        svc = ocr.OCRService()
        text = "\n".join(["", "sku: NO-NAME", "price: 3", "3 3.00", "   "])
        assert svc.extract_products_from_text(text) == []


class TestPipelines:
    def test_image_pipeline_delegates_to_text_extraction(self):
        svc = ocr.OCRService()
        with patch.object(svc, "extract_text_from_image", return_value="Product Name: P\nprice: 1") as extract:
            products = svc.extract_products_from_image(b"img")
        assert products == [{"name": "P", "price": "1"}]
        extract.assert_called_once_with(b"img")

    def test_pdf_pipeline_combines_page_products(self):
        svc = ocr.OCRService()
        with patch.object(svc, "extract_text_from_pdf", return_value=["Product Name: A", "Product Name: B"]) as extract:
            products = svc.extract_products_from_pdf(b"pdf")
        assert products == [{"name": "A"}, {"name": "B"}]
        extract.assert_called_once_with(b"pdf")

    def test_pdf_pipeline_with_no_pages(self):
        svc = ocr.OCRService()
        with patch.object(svc, "extract_text_from_pdf", return_value=[]):
            assert svc.extract_products_from_pdf(b"pdf") == []


class TestParseInvoiceTable:
    def test_header_detection_and_column_splitting(self):
        svc = ocr.OCRService()
        text = "\n".join(
            [
                "random preamble",
                "product    qty    price    total",
                "Widget A    2    10.50    21.00",
                "Gadget B    1    5.00",
                "total    26.00",
            ]
        )
        assert svc.parse_invoice_table(text) == [
            {"name": "Widget A", "quantity": "2", "price": "10.50", "total": "21.00"},
            {"name": "Gadget B", "quantity": "1", "price": "5.00", "total": ""},
        ]

    def test_no_header_falls_back_to_field_extraction(self):
        svc = ocr.OCRService()
        with patch.object(svc, "extract_products_from_text", return_value=[{"name": "Fallback"}]) as fallback:
            assert svc.parse_invoice_table("no header") == [{"name": "Fallback"}]
        fallback.assert_called_once_with("no header")

    def test_blank_line_after_header_stops_parsing(self):
        svc = ocr.OCRService()
        assert svc.parse_invoice_table("product    qty\n\nWidget A    2    3.00") == []


class TestInvoiceParser:
    @staticmethod
    def _ocr(image_text="", pdf_texts=None):
        fake = MagicMock()
        fake.extract_text_from_image.return_value = image_text
        fake.extract_text_from_pdf.return_value = pdf_texts if pdf_texts is not None else []
        fake.extract_products_from_text.return_value = [{"name": "Widget"}]
        return fake

    def test_init_holds_the_ocr_service(self):
        fake = self._ocr()
        assert ocr.InvoiceParser(fake).ocr is fake

    def test_parse_image_invoice(self):
        text = "\n".join(
            [
                "Supplier: Acme Corp",
                "Invoice #: INV-123",
                "Date: 12/03/2025",
                "Total: 1,234.56",
                "Product Name: Widget",
            ]
        )
        fake = self._ocr(image_text=text)
        result = ocr.InvoiceParser(fake).parse_invoice(b"bytes", "scan.PNG")
        assert result["supplier"] == "Acme Corp"
        assert result["invoice_number"] == "INV-123"
        assert result["date"] == "12/03/2025"
        assert result["total"] == Decimal("1234.56")
        assert result["products"] == [{"name": "Widget"}]
        assert result["raw_text"] == text
        fake.extract_text_from_image.assert_called_once_with(b"bytes")
        fake.extract_text_from_pdf.assert_not_called()

    def test_parse_pdf_invoice_joins_pages(self):
        fake = self._ocr(pdf_texts=["page one", "page two"])
        result = ocr.InvoiceParser(fake).parse_invoice(b"bytes", "INVOICE.PDF")
        assert result["raw_text"] == "page one\npage two"
        assert result["supplier"] is None
        assert result["total"] is None
        assert result["products"] == [{"name": "Widget"}]
        fake.extract_text_from_pdf.assert_called_once_with(b"bytes")
        fake.extract_text_from_image.assert_not_called()


class TestInvoiceFieldExtractors:
    @staticmethod
    def _parser():
        return ocr.InvoiceParser(MagicMock())

    def test_supplier_patterns(self):
        parser = self._parser()
        assert parser._extract_supplier("المورد: Acme") == "Acme"
        assert parser._extract_supplier("Company: Beta") == "Beta"
        assert parser._extract_supplier("nothing here") is None

    def test_invoice_number_patterns(self):
        parser = self._parser()
        assert parser._extract_invoice_number("Invoice #: INV-123") == "INV-123"
        # The longer label must win over the generic "Invoice #" alternative.
        assert parser._extract_invoice_number("Invoice number: INV-9") == "INV-9"
        assert parser._extract_invoice_number("فاتورة رقم F-9") == "F-9"
        assert parser._extract_invoice_number("nothing") is None

    def test_date_patterns(self):
        parser = self._parser()
        assert parser._extract_date("date: 12/03/2025") == "12/03/2025"
        assert parser._extract_date("تاريخ: 1-2-2024") == "1-2-2024"
        assert parser._extract_date("nothing") is None

    def test_total_patterns(self):
        parser = self._parser()
        assert parser._extract_total("total: 1,234.56") == Decimal("1234.56")
        assert parser._extract_total("net: 99.50") == Decimal("99.50")
        assert parser._extract_total("nothing") is None
