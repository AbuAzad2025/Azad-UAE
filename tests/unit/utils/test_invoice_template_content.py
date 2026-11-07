"""Every selectable invoice template must render its shared document body."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape


@pytest.mark.parametrize("template", ["modern", "classic", "gulf", "minimal", "simple"])
def test_invoice_contains_sale_and_tenant_settings(template):
    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[3] / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals.update(
        t=lambda key: key,
        csp_nonce=lambda: "test-nonce",
        dist_url=lambda name: f"/static/{name}",
        url_for=lambda endpoint, **kwargs: "/static/asset",
        tenant_document_logo=lambda settings, tenant_id: "",
        format_currency=lambda amount, currency: f"{amount} {currency}",
        get_system_default_currency=lambda: "AED",
    )
    line = SimpleNamespace(
        product=SimpleNamespace(name="Product A"),
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        discount_percent=Decimal("0"),
        line_total=Decimal("100"),
    )
    sale = SimpleNamespace(
        sale_number="SALE-UNIQUE-42",
        sale_date=datetime(2026, 1, 1),
        branch=None,
        customer=None,
        seller=None,
        currency="AED",
        subtotal=Decimal("100"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_amount=Decimal("5"),
        tax_rate=Decimal("5"),
        total_amount=Decimal("105"),
        lines=[line],
        payments=[],
        notes="",
    )
    settings = SimpleNamespace(
        header_color="#123456",
        accent_color="#654321",
        company_name_ar="Tenant A & Co",
        address_ar="Tenant address",
        phone_1="0501234567",
        phone_2="",
        email="tenant@example.com",
        website="",
        tax_number="TRN-42",
        show_logo=False,
        watermark_text="",
        enable_watermark=False,
        payment_terms_ar="Payment terms A",
        bank_name="Tenant bank A",
        bank_account_number="12345",
        iban="AE-IBAN-A",
        swift_code="SWIFT-A",
        commercial_register="",
        license_number="",
        default_invoice_note_ar="Invoice note A",
        footer_text_ar="Footer A",
        facebook_url="",
        instagram_url="",
        whatsapp_number="",
    )
    html = env.get_template(f"invoices/{template}.html").render(
        sale=sale,
        settings=settings,
        print_branch=None,
        print_user_name="Cashier",
        tenant_default_currency="AED",
        qr_data_url="",
        amount_in_words="",
    )

    assert "SALE-UNIQUE-42" in html
    assert "Product A" in html
    assert "Tenant A &amp; Co" in html
    assert "TRN-42" in html
    assert "105 AED" in html
    assert "Tenant bank A" in html and "AE-IBAN-A" in html
    assert "Payment terms A" in html and "Invoice note A" in html and "Footer A" in html
