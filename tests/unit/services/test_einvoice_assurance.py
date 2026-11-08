"""E-invoice — strategy routing, statutory XML/QR artifacts, persistence."""

from __future__ import annotations

import base64
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest


def _tlv_items(payload_b64: str) -> dict[int, bytes]:
    raw = base64.b64decode(payload_b64)
    items = {}
    index = 0
    while index < len(raw):
        tag = raw[index]
        length = raw[index + 1]
        items[tag] = raw[index + 2 : index + 2 + length]
        index += 2 + length
    return items


@pytest.fixture
def ae_sale(db_session, sample_branch, sample_tenant, sample_user):
    from models import Customer, Product, Sale, SaleLine

    # AE tenant from the sample fixture is the right country for a statutory
    # artifact test; it is provisioned with its GL chart already.
    tenant = sample_tenant
    tenant.tax_number = "300000000000003"
    tenant.vat_number = "300000000000003"
    product = Product(tenant_id=tenant.id, name="Widget", regular_price=Decimal("1000"))
    db_session.add(product)
    customer = Customer(tenant_id=tenant.id, name="Buyer Co", phone="0500000000")
    db_session.add(customer)
    db_session.flush()

    sale = Sale(
        tenant_id=tenant.id,
        customer_id=customer.id,
        seller_id=sample_user.id,
        sale_number="INV-TEST-1",
        branch_id=sample_branch.id,
        currency="AED",
        base_currency="AED",
        amount=Decimal("1050"),
        amount_aed=Decimal("1050"),
        subtotal=Decimal("1000"),
        tax_rate=Decimal("5"),
        tax_amount=Decimal("50"),
        taxable_amount=Decimal("1000"),
        total_amount=Decimal("1050"),
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal("2"),
        unit_price=Decimal("500"),
        line_total=Decimal("1000"),
    )
    db_session.add(line)
    db_session.flush()
    sale.lines = [line]
    sale.customer = customer
    return sale


class TestStaticArtifacts:
    """Document builder — no services involved."""

    def test_zatca_tlv_round_trip(self):
        from utils.einvoice_document import invoice_sha256_hex, zatca_tlv_base64

        qr = zatca_tlv_base64(
            "ACME SA", "300000000000003", "2026-11-09T10:00:00Z", Decimal("1150"), Decimal("150"), "aGVsbG8="
        )
        items = _tlv_items(qr)
        assert items[1] == b"ACME SA"
        assert items[2] == b"300000000000003"
        assert items[3] == b"2026-11-09T10:00:00Z"
        assert items[4] == b"1150.00"
        assert items[5] == b"150.00"
        assert items[6] == b"aGVsbG8="
        assert len(invoice_sha256_hex("<Invoice/>")) == 64

    def test_build_invoice_xml_is_wellformed_and_namespaced(self, ae_sale):
        from utils.einvoice_document import build_invoice_xml, invoice_sha256_hex

        xml_text = build_invoice_xml(
            ae_sale, None, country="AE", currency="AED", profile_id="reporting", doc_type="invoice"
        )
        root = ET.fromstring(xml_text)
        cbc = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
        assert root.find(f"{cbc}ID").text == "INV-TEST-1"
        assert root.find(f"{cbc}DocumentCurrencyCode").text == "AED"
        assert invoice_sha256_hex(xml_text) == invoice_sha256_hex(xml_text)


class TestStrategies:
    """Every supported country produces a real artifact."""

    def test_ae_generates_fta_ubl(self, ae_sale):
        from utils.localization.uae import UAEStrategy

        result = UAEStrategy().generate_einvoice(ae_sale)
        assert result["format"] == "fta_ubl_xml"
        assert result["qr_base64"] == ""
        ET.fromstring(result["xml_payload"])
        assert len(result["invoice_hash"]) == 64

    def test_ksa_generates_zatca_qr(self, ae_sale):
        from utils.localization.ksa import KSAStrategy

        result = KSAStrategy().generate_einvoice(ae_sale)
        assert result["format"] == "zatca_ubl_simplified_xml"
        items = _tlv_items(result["qr_base64"])
        assert set(items) == {1, 2, 3, 4, 5, 6}
        assert items[1] and items[2]  # seller name + VAT number present
        assert len(items[3]) == 20 and items[3].endswith(b"Z")  # ISO-8601 UTC
        assert items[4] == b"1050.00"
        assert items[5] == b"50.00"
        ET.fromstring(result["xml_payload"])

    def test_ps_generates_pma_ubl(self, ae_sale):
        from utils.localization.palestine import PalestineStrategy

        result = PalestineStrategy().generate_einvoice(ae_sale)
        assert result["format"] == "pma_ubl_xml"
        ET.fromstring(result["xml_payload"])

    def test_il_generates_il_ubl(self, ae_sale):
        from utils.localization.israel import IsraelStrategy

        result = IsraelStrategy().generate_einvoice(ae_sale)
        assert result["format"] == "il_ubl_xml"
        ET.fromstring(result["xml_payload"])

    def test_xx_raises_not_implemented(self, ae_sale):
        from utils.localization.null import NullStrategy

        with pytest.raises(NotImplementedError):
            NullStrategy().generate_einvoice(ae_sale)


class TestGenerateForSale:
    """Persistence via the real service path."""

    def test_unsupported_country_is_a_noop(self, db_session, ae_sale, mocker):
        mocker.patch("utils.tax_settings.vat_country", return_value="XX")
        ae_sale.tenant.vat_country = "XX"
        from services.einvoice_service import EInvoiceService

        assert EInvoiceService.generate_for_sale(ae_sale) is None

    def test_supported_country_persists_row(self, db_session, ae_sale, mocker):
        mocker.patch("utils.tax_settings.vat_country", return_value="AE")
        from services.einvoice_service import EInvoiceService

        row = EInvoiceService.generate_for_sale(ae_sale)
        assert row is not None
        assert row.country == "AE"
        assert row.format == "fta_ubl_xml"
        assert len(row.invoice_hash) == 64
        assert row.xml_payload.startswith("<?xml")
        assert "INV-TEST-1" in row.xml_payload

    def test_regeneration_updates_the_same_row(self, db_session, ae_sale, mocker):
        mocker.patch("utils.tax_settings.vat_country", return_value="AE")
        from services.einvoice_service import EInvoiceService

        first = EInvoiceService.generate_for_sale(ae_sale)
        second = EInvoiceService.generate_for_sale(ae_sale)
        assert first.id == second.id

    def test_supported_country_failure_propagates(self, db_session, ae_sale, mocker):
        mocker.patch("utils.tax_settings.vat_country", return_value="AE")
        strategy = mocker.MagicMock()
        strategy.generate_einvoice.side_effect = ValueError("broken document")
        mocker.patch("utils.localization.get_strategy", return_value=strategy)

        from services.einvoice_service import EInvoiceService

        with pytest.raises(ValueError, match="broken document"):
            EInvoiceService.generate_for_sale(ae_sale)
