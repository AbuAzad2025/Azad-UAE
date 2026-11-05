"""OCR Service for invoice/box scanning and product extraction."""

from __future__ import annotations

import io
import logging
import os
import re
from decimal import Decimal

logger = logging.getLogger(__name__)

# Optional imports - OCR is optional feature
try:
    import pytesseract
    from PIL import Image

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract/PIL not available - OCR features disabled")


class OCRService:
    """OCR service for extracting product data from invoices and boxes."""

    # Arabic/English field patterns
    FIELD_PATTERNS = {
        "name": [
            r"(?:اسم\s*المنتج|product\s*name|اسم)\s*[:：]\s*(.+)",
            r"(?: الصنف|item)\s*[:：]\s*(.+)",
        ],
        "sku": [
            r"(?:sku|رمز|كود)\s*[:：]\s*([A-Z0-9\-]+)",
        ],
        "barcode": [
            r"(?:barcode|الباركود|الباركود)\s*[:：]\s*(\d{8,14})",
        ],
        "price": [
            r"(?:السعر|price|سعر)\s*[:：]\s*(\d+(?:\.\d+)?)",
        ],
        "cost": [
            r"(?:التكلفة|cost|كلفة)\s*[:：]\s*(\d+(?:\.\d+)?)",
        ],
        "quantity": [
            r"(?:الكمية|quantity|qty)\s*[:：]\s*(\d+(?:\.\d+)?)",
        ],
        "category": [
            r"(?:التصنيف|category|الصنف)\s*[:：]\s*(.+)",
        ],
    }

    def __init__(self, lang: str = "ara+eng"):
        self.lang = lang
        self._tesseract_path = os.environ.get("TESSERACT_CMD", "tesseract")

    @staticmethod
    def is_available() -> bool:
        return TESSERACT_AVAILABLE

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Extract text from image using Tesseract OCR."""
        if not TESSERACT_AVAILABLE:
            raise RuntimeError("Tesseract OCR not available. Install pytesseract and tesseract-ocr.")

        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Preprocess for better OCR
            image = self._preprocess_image(image)
            text = pytesseract.image_to_string(image, lang=self.lang, config="--psm 6")
            return text
        except Exception as e:
            logger.exception(f"OCR failed: {e}")
            raise

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for better OCR accuracy."""
        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")

        # Enhance contrast
        from PIL import ImageEnhance

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)

        # Resize if too small
        width, height = image.size
        if width < 1000:
            scale = 1000 / width
            image = image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

        return image

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> list[str]:
        """Extract text from each page of a PDF."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page to image
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                text = self.extract_text_from_image(img_bytes)
                texts.append(text)
            doc.close()
            return texts
        except ImportError:
            logger.warning("PyMuPDF not available for PDF OCR")
            return []

    def extract_products_from_text(self, text: str) -> list[dict]:
        """Extract product information from OCR text."""
        products = []

        # Try to find table-like structures
        lines = text.split("\n")
        current_product = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to match known patterns
            for field, patterns in self.FIELD_PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        value = match.group(1).strip()
                        if value:
                            current_product[field] = value
                            break

            # If line looks like a product row (has price and qty)
            if re.search(r"\d+(?:\.\d+)?\s+[\d,]+\.?\d*", line) and len(current_product) >= 2:
                if "name" in current_product:
                    products.append(current_product.copy())
                    current_product = {}

        # Don't forget the last product
        if current_product and "name" in current_product:
            products.append(current_product)

        return products

    def extract_products_from_image(self, image_bytes: bytes) -> list[dict]:
        """Full pipeline: image -> text -> products."""
        text = self.extract_text_from_image(image_bytes)
        return self.extract_products_from_text(text)

    def extract_products_from_pdf(self, pdf_bytes: bytes) -> list[dict]:
        """Full pipeline: PDF -> pages -> text -> products."""
        all_products = []
        texts = self.extract_text_from_pdf(pdf_bytes)
        for text in texts:
            products = self.extract_products_from_text(text)
            all_products.extend(products)
        return all_products

    def parse_invoice_table(self, text: str) -> list[dict]:
        """Parse structured table from invoice text."""
        products = []
        lines = text.split("\n")

        # Look for table headers
        header_idx = -1
        for i, line in enumerate(lines):
            if any(
                h in line.lower() for h in ["المنتج", "product", "الصنف", "item", "الكمية", "qty", "السعر", "price"]
            ):
                header_idx = i
                break

        if header_idx == -1:
            return self.extract_products_from_text(text)

        # Parse rows after header
        for line in lines[header_idx + 1 :]:
            line = line.strip()
            if not line or line.startswith(("الاجمالي", "total", "المجموع")):
                break

            # Split by multiple spaces or tabs
            parts = re.split(r"\s{2,}|\t+", line)
            parts = [p.strip() for p in parts if p.strip()]

            if len(parts) >= 3:
                product = {
                    "name": parts[0] if len(parts) > 0 else "",
                    "quantity": parts[1] if len(parts) > 1 else "",
                    "price": parts[2] if len(parts) > 2 else "",
                    "total": parts[3] if len(parts) > 3 else "",
                }
                if product["name"]:
                    products.append(product)

        return products


class InvoiceParser:
    """Specialized parser for supplier invoices."""

    def __init__(self, ocr_service: OCRService):
        self.ocr = ocr_service

    def parse_invoice(self, file_bytes: bytes, filename: str) -> dict:
        """Parse invoice and return structured data."""
        ext = filename.lower().split(".")[-1]

        if ext == "pdf":
            text = "\n".join(self.ocr.extract_text_from_pdf(file_bytes))
        else:
            text = self.ocr.extract_text_from_image(file_bytes)

        return {
            "supplier": self._extract_supplier(text),
            "invoice_number": self._extract_invoice_number(text),
            "date": self._extract_date(text),
            "total": self._extract_total(text),
            "products": self.ocr.extract_products_from_text(text),
            "raw_text": text,
        }

    def _extract_supplier(self, text: str) -> str | None:
        patterns = [
            r"(?:المورد|supplier|المورد)\s*[:：]\s*(.+)",
            r"(?:شركة|company)\s*[:：]\s*(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_invoice_number(self, text: str) -> str | None:
        patterns = [
            r"(?:رقم\s*الفاتورة|invoice\s*#?|invoice\s*number)\s*[:：\s]*(\S+)",
            r"(?:فاتورة\s*رقم)\s*[:：\s]*(\S+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_date(self, text: str) -> str | None:
        patterns = [
            r"(?:التاريخ|date)\s*[:：]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(?:تاريخ)\s*[:：]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_total(self, text: str) -> Decimal | None:
        patterns = [
            r"(?:الاجمالي|total|المجموع)\s*[:：]\s*(\d+(?:,\d{3})*(?:\.\d+)?)",
            r"(?:صافي|net)\s*[:：]\s*(\d+(?:,\d{3})*(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return Decimal(match.group(1).replace(",", ""))
        return None
