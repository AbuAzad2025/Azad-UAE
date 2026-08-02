"""
Visual Render & PDF Export Audit Script
Renders all invoice/receipt templates with realistic Arabic dummy data
for manual visual inspection in a browser.
"""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils.i18n import t
from utils.helpers import format_currency, format_date, format_datetime, format_time, format_number

# ── Setup paths ──
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.makedirs("audit_output", exist_ok=True)

# ── Create Jinja2 environment directly (no Flask routing needed) ──
jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(project_root, "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

# Register template globals / filters
jinja_env.globals["t"] = t
jinja_env.globals["current_user"] = MagicMock(is_authenticated=False)
jinja_env.globals["url_for"] = lambda endpoint, **kwargs: f"/static/{kwargs.get('filename', '')}" if endpoint == "static" else f"/{endpoint}"

# Flask config mock for standalone rendering
jinja_env.globals["config"] = MagicMock(
    DEVELOPER_CREDIT="Powered by Azad Intelligent Systems",
    DEVELOPER_NAME_AR="آزاد",
    DEVELOPER_NAME="Azad",
    DEVELOPER_PHONE="",
    DEVELOPER_EMAIL="",
    DEVELOPER_WEBSITE="https://azad.ae",
    DEVELOPER_WHATSAPP="",
    DEVELOPER_LOGO="assets/brand/azad/logos/logo.png",
)

# tenant_document_logo depends on utils.tenant_branding which depends on Flask cache
# For standalone rendering, return empty string (logo will be skipped)
jinja_env.globals["tenant_document_logo"] = lambda settings=None, tenant_id=None: ""

# These helpers are used as both filters and callable globals in templates
jinja_env.globals["format_currency"] = format_currency
jinja_env.globals["format_date"] = format_date
jinja_env.globals["format_datetime"] = format_datetime
jinja_env.globals["format_time"] = format_time
jinja_env.globals["format_number"] = format_number

# Flask context processors inject `now` as datetime.now
jinja_env.globals["now"] = datetime.now

jinja_env.filters.setdefault("format_currency", format_currency)
jinja_env.filters.setdefault("format_date", format_date)
jinja_env.filters.setdefault("format_datetime", format_datetime)
jinja_env.filters.setdefault("format_time", format_time)
jinja_env.filters.setdefault("format_number", format_number)


# ── Build dummy objects ──
def _make_customer():
    c = MagicMock()
    c.name = "شركة الأمل التجارية"
    c.phone = "+971501234567"
    c.email = "info@alamal.ae"
    c.address = "دبي، شارع الشيخ زايد، برج الأمل"
    return c


def _make_product(name, code=""):
    p = MagicMock()
    p.name = name
    p.code = code
    return p


def _make_user():
    u = MagicMock()
    u.full_name = "أحمد محمد"
    u.username = "ahmed.m"
    return u


def _make_payment():
    p = MagicMock()
    p.payment_number = "PAY-2026-001"
    p.payment_date = datetime(2026, 8, 2, 14, 30, tzinfo=timezone.utc)
    p.amount_aed = Decimal("1250.500")
    p.payment_method = "cheque"
    p.cheque_number = "CHK-884422"
    p.cheque_date = datetime(2026, 8, 15, tzinfo=timezone.utc).date()
    p.bank_name = "بنك الإمارات دبي الوطني"
    p.reference_number = "REF-9911"
    p.currency = "AED"
    return p


def _make_settings():
    s = MagicMock()
    s.company_name_ar = "مؤسسة آزاد للحلول الذكية"
    s.address_ar = "دبي، واحة دبي للسيليكون، المبنى ٣"
    s.phone_1 = "+97145678900"
    s.phone_2 = "+97145678901"
    s.email = "info@azad.ae"
    s.website = "https://azad.ae"
    s.tax_number = "1234567890123"
    s.bank_name = "بنك أبوظبي الأول"
    s.iban = "AE070331234567890123456"
    s.swift_code = "FABAAEAD"
    s.bank_account_number = "0123456789"
    s.commercial_register = "CR-12345"
    s.license_number = "LIC-98765"
    s.header_color = "#2c3e50"
    s.accent_color = "#3498db"
    s.payment_terms_ar = "الدفع خلال 30 يوماً من تاريخ الفاتورة"
    s.default_invoice_note_ar = "شكراً لتعاملكم معنا"
    s.default_receipt_note_ar = "تم استلام المبلغ حسب البيانات أعلاه"
    s.footer_text_ar = "نظام آزاد المحاسبي — جميع الحقوق محفوظة"
    s.facebook_url = "https://facebook.com/azad"
    s.instagram_url = "https://instagram.com/azad"
    s.whatsapp_number = "+971501112233"
    s.paper_size = "A4"
    s.orientation = "portrait"
    s.enable_watermark = False
    s.watermark_text = ""
    s.watermark_image_path = ""
    return s


def _make_sale():
    sale = MagicMock()
    sale.id = 1
    sale.sale_number = "INV-2026-00842"
    sale.sale_date = datetime(2026, 8, 2, 10, 15, tzinfo=timezone.utc)
    sale.currency = "ILS"
    sale.subtotal = Decimal("4850.000")
    sale.discount_amount = Decimal("350.000")
    sale.shipping_cost = Decimal("120.000")
    sale.tax_rate = Decimal("17.00")
    sale.tax_amount = Decimal("777.000")
    sale.total_amount = Decimal("5397.000")
    sale.notes = "يرجى التواصل للاستفسارات على الرقم 0501234567"
    sale.customer = _make_customer()
    sale.seller = _make_user()
    sale.branch = None

    line1 = MagicMock()
    line1.product = _make_product("لابتوب Dell Latitude 7440", "DLT-7440")
    line1.quantity = Decimal("2.000")
    line1.unit_price = Decimal("4500.000")
    line1.discount_percent = Decimal("5.00")
    line1.line_total = Decimal("8550.000")

    line2 = MagicMock()
    line2.product = _make_product("ماوس لاسلكي Logitech MX Master 3", "LOG-MX3")
    line2.quantity = Decimal("3.000")
    line2.unit_price = Decimal("350.000")
    line2.discount_percent = Decimal("0")
    line2.line_total = Decimal("1050.000")

    line3 = MagicMock()
    line3.product = _make_product('شاشة 27" Samsung Odyssey', "SAM-OD27")
    line3.quantity = Decimal("1.000")
    line3.unit_price = Decimal("1850.000")
    line3.discount_percent = Decimal("10.00")
    line3.line_total = Decimal("1665.000")

    sale.lines = [line1, line2, line3]
    sale.payments = [_make_payment()]
    return sale


def _make_receipt():
    r = MagicMock()
    r.id = 1
    r.receipt_number = "RCV-2026-00156"
    r.receipt_date = datetime(2026, 8, 2, 11, 45, tzinfo=timezone.utc)
    r.amount = Decimal("3500.000")
    r.base_amount = Decimal("3500.000")
    r.amount_aed = Decimal("3500.000")
    r.currency = "AED"
    r.payment_method = "cheque"
    r.cheque_number = "CHK-442211"
    r.cheque_date = datetime(2026, 8, 20, tzinfo=timezone.utc).date()
    r.bank_name = "بنك دبي الإسلامي"
    r.reference_number = "REF-5566"
    r.notes = "دفعة جزئية على فاتورة INV-2026-00842"
    r.customer = _make_customer()
    r.user = _make_user()
    r.branch = None

    def _get_source_info():
        return {
            "type": "فاتورة بيع",
            "number": "INV-2026-00842",
            "date": "2026-08-02",
            "amount": 5397.0,
        }

    r.get_source_info = _get_source_info
    return r


# ── Shared context ──
SHARED_CONTEXT = {
    "tenant_name_ar": "مؤسسة آزاد للحلول الذكية",
    "tenant_name": "Azad Intelligent Systems",
    "tenant_phone": "+97145678900",
    "tenant_email": "info@azad.ae",
    "tenant_address": "دبي، واحة دبي للسيليكون، المبنى ٣",
    "tenant_default_currency": "AED",
    "tenant_currency_name_ar": "درهم إماراتي",
    "company_name_ar": "مؤسسة آزاد للحلول الذكية",
    "company_name": "Azad Intelligent Systems",
    "company_phone": "+97145678900",
    "company_email": "info@azad.ae",
    "company_address": "دبي، واحة دبي للسيليكون، المبنى ٣",
    "print_user_name": "أحمد محمد",
    "print_branch": None,
    "current_language": "ar",
    "is_rtl": True,
    "settings": _make_settings(),
    "developer_credit": "Powered by Azad Intelligent Systems",
    "developer_name_ar": "آزاد",
    "developer_name": "Azad",
    "developer_phone": "",
    "developer_email": "",
    "developer_website": "https://azad.ae",
    "developer_whatsapp": "",
    "developer_logo": "assets/brand/azad/logos/logo.png",
}

INVOICE_TEMPLATES = ["modern", "classic", "gulf", "minimal", "simple"]
RECEIPT_TEMPLATES = ["modern", "classic", "gulf", "minimal", "simple"]

# ── Render ──
print("\n=== RENDERING INVOICE TEMPLATES ===")
for tmpl_name in INVOICE_TEMPLATES:
    ctx = dict(SHARED_CONTEXT)
    ctx["sale"] = _make_sale()
    try:
        html = jinja_env.get_template(f"invoices/{tmpl_name}.html").render(ctx)
        out_path = f"audit_output/invoice_{tmpl_name}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ invoices/{tmpl_name}.html  →  {out_path}")
    except Exception as e:
        import traceback

        print(f"  ✗ invoices/{tmpl_name}.html  ERROR: {e}")
        traceback.print_exc()
        print()

print("\n=== RENDERING RECEIPT TEMPLATES ===")
for tmpl_name in RECEIPT_TEMPLATES:
    ctx = dict(SHARED_CONTEXT)
    ctx["receipt"] = _make_receipt()
    ctx["doc_number"] = "RCV-2026-00156"
    ctx["amount_in_words"] = "ثلاثة آلاف وخمسمائة درهم إماراتي"
    try:
        html = jinja_env.get_template(f"receipts/{tmpl_name}.html").render(ctx)
        out_path = f"audit_output/receipt_{tmpl_name}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ receipts/{tmpl_name}.html  →  {out_path}")
    except Exception as e:
        import traceback

        print(f"  ✗ receipts/{tmpl_name}.html  ERROR: {e}")
        traceback.print_exc()
        print()

print("\n=== AUDIT COMPLETE ===")
print("Open the files in audit_output/ in your browser for visual inspection.")
print("Absolute path:", os.path.abspath("audit_output"))
