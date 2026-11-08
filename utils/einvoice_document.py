"""Statutory e-invoice document builder — shared by all supported countries.

Produces one artifact: a UBL 2.1-shaped ``Invoice`` carrying the statutory
parties, lines, totals and VAT breakdown, plus a tamper-evident SHA-256 hash
of the XML. Where the jurisdiction mandates a machine-readable QR (KSA
ZATCA simplified invoices), the TLV payload is built here too — tags 1-6
per the published ZATCA specification (tags 7-9 need the tenant's CSID, which
is issued by ZATCA during onboarding and is out of offline scope).

Government-gateway submission (ZATCA Phase 2 signing, Israel Tax Authority
allocation number, PMA/FTA access points) is a separate, credential-gated
phase. Nothing here marks a document as government-accepted.
"""

from __future__ import annotations

import base64
import hashlib
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree as ET

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

ET.register_namespace("", UBL_NS)
ET.register_namespace("cac", CAC_NS)
ET.register_namespace("cbc", CBC_NS)


def _q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _text(parent, tag, value, ns=None, **attrib):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}" if ns else tag, {k: str(v) for k, v in attrib.items()})
    el.text = str(value)
    return el


def _tlv(tag: int, value: bytes) -> bytes:
    if len(value) > 255:
        value = value[:255]
    return bytes([tag, len(value)]) + value


def zatca_tlv_base64(
    seller_name: str,
    vat_number: str,
    timestamp_iso: str,
    total_with_vat: Decimal,
    vat_amount: Decimal,
    xml_sha256_b64: str,
) -> str:
    """ZATCA simplified-invoice QR — TLV (tags 1-6), base64-encoded."""
    payload = b"".join(
        [
            _tlv(1, str(seller_name).encode("utf-8")),
            _tlv(2, str(vat_number).encode("utf-8")),
            _tlv(3, timestamp_iso.encode("utf-8")),
            _tlv(4, f"{_q2(total_with_vat)}".encode()),
            _tlv(5, f"{_q2(vat_amount)}".encode()),
            _tlv(6, xml_sha256_b64.encode("utf-8")),
        ]
    )
    return base64.b64encode(payload).decode("ascii")


def build_invoice_xml(
    sale, tenant, *, country: str, currency: str, profile_id: str = "reporting", doc_type_code: str = "388"
) -> str:
    """UBL 2.1-shaped invoice document for a posted sale.

    ``profile_id``/``doc_type_code`` carry the jurisdiction's document
    vocabulary — KSA asks for ``reporting``/388, the others accept the
    generic values. Statutory fields (seller TRN, buyer TRN when present,
    lines, VAT breakdown, totals) are always populated from the sale.
    """
    tenant_name = (
        (getattr(tenant, "name_en", None) or "").strip()
        or (getattr(tenant, "name", None) or "").strip()
        or (getattr(tenant, "name_ar", None) or "").strip()
        if tenant
        else ""
    )
    seller_id = (
        (getattr(tenant, "tax_number", None) or getattr(tenant, "vat_number", None) or "").strip() if tenant else ""
    )
    customer = getattr(sale, "customer", None)
    buyer_name = (getattr(customer, "name", None) or "").strip()
    buyer_id = (getattr(customer, "tax_number", None) or "").strip()
    issue_dt = getattr(sale, "sale_date", None)
    issue_date = issue_dt.strftime("%Y-%m-%d") if issue_dt else ""
    issue_time = issue_dt.strftime("%H:%M:%S") if issue_dt else ""

    rate = Decimal(str(getattr(sale, "tax_rate", 0) or 0))
    total = _q3(getattr(sale, "total_amount", 0))
    tax_amount = _q3(getattr(sale, "tax_amount", 0))
    taxable = _q3(getattr(sale, "taxable_amount", 0) or (total - tax_amount))
    line_extension = _q3(
        getattr(sale, "subtotal", 0)
        or sum((Decimal(str(getattr(ln, "line_total", 0) or 0)) for ln in getattr(sale, "lines", [])), Decimal("0"))
    )

    root = ET.Element(f"{{{UBL_NS}}}Invoice")
    _text(root, "ProfileID", profile_id, CBC_NS)
    _text(root, "ID", getattr(sale, "sale_number", ""), CBC_NS)
    _text(root, "IssueDate", issue_date, CBC_NS)
    _text(root, "IssueTime", issue_time, CBC_NS)
    _text(root, "InvoiceTypeCode", doc_type_code, CBC_NS)
    _text(root, "DocumentCurrencyCode", currency, CBC_NS)
    _text(root, "TaxCurrencyCode", currency, CBC_NS)

    supplier = ET.SubElement(root, f"{{{CAC_NS}}}AccountingSupplierParty")
    party = ET.SubElement(supplier, f"{{{CAC_NS}}}Party")
    _text(ET.SubElement(party, f"{{{CAC_NS}}}PartyName"), "Name", tenant_name, CBC_NS)
    address = ET.SubElement(party, f"{{{CAC_NS}}}PostalAddress")
    _text(
        address,
        "StreetName",
        ((getattr(tenant, "address_en", None) or getattr(tenant, "address_ar", None) or "").strip()) if tenant else "",
        CBC_NS,
    )
    _text(address, "CityName", (getattr(tenant, "city", None) or "").strip() if tenant else "", CBC_NS)
    _text(address, "CountryIdentificationCode", country, CBC_NS)
    tax_scheme = ET.SubElement(party, f"{{{CAC_NS}}}PartyTaxScheme")
    _text(tax_scheme, "CompanyID", seller_id, CBC_NS)
    scheme = ET.SubElement(tax_scheme, f"{{{CAC_NS}}}TaxScheme")
    _text(scheme, "ID", "VAT", CBC_NS)

    customer_party = ET.SubElement(root, f"{{{CAC_NS}}}AccountingCustomerParty")
    cparty = ET.SubElement(customer_party, f"{{{CAC_NS}}}Party")
    _text(ET.SubElement(cparty, f"{{{CAC_NS}}}PartyName"), "Name", buyer_name or "Walk-in Customer", CBC_NS)
    if buyer_id:
        ctax = ET.SubElement(cparty, f"{{{CAC_NS}}}PartyTaxScheme")
        _text(ctax, "CompanyID", buyer_id, CBC_NS)
        cscheme = ET.SubElement(ctax, f"{{{CAC_NS}}}TaxScheme")
        _text(cscheme, "ID", "VAT", CBC_NS)

    for index, line in enumerate(getattr(sale, "lines", []) or [], start=1):
        product = getattr(line, "product", None)
        name = (getattr(product, "name", None) or f"Item {getattr(line, 'product_id', index)}").strip()
        invoice_line = ET.SubElement(root, f"{{{CAC_NS}}}InvoiceLine")
        _text(invoice_line, "ID", index, CBC_NS)
        _text(
            invoice_line,
            "InvoicedQuantity",
            f"{_q3(getattr(line, 'quantity', 0))}",
            CBC_NS,
            unitCode="PCE",
        )
        _text(
            invoice_line, "LineExtensionAmount", f"{_q3(getattr(line, 'line_total', 0))}", CBC_NS, currencyID=currency
        )
        item = ET.SubElement(invoice_line, f"{{{CAC_NS}}}Item")
        _text(item, "Name", name, CBC_NS)
        price = ET.SubElement(invoice_line, f"{{{CAC_NS}}}Price")
        _text(price, "PriceAmount", f"{_q3(getattr(line, 'unit_price', 0))}", CBC_NS, currencyID=currency)

    tax_total = ET.SubElement(root, f"{{{CAC_NS}}}TaxTotal")
    _text(tax_total, "TaxAmount", f"{_q3(tax_amount)}", CBC_NS, currencyID=currency)
    subtotal = ET.SubElement(tax_total, f"{{{CAC_NS}}}TaxSubtotal")
    _text(subtotal, "TaxableAmount", f"{_q3(taxable)}", CBC_NS, currencyID=currency)
    _text(subtotal, "TaxAmount", f"{_q3(tax_amount)}", CBC_NS, currencyID=currency)
    category = ET.SubElement(subtotal, f"{{{CAC_NS}}}TaxCategory")
    _text(category, "ID", "S", CBC_NS)
    _text(category, "Percent", f"{rate}", CBC_NS)
    tax_scheme2 = ET.SubElement(category, f"{{{CAC_NS}}}TaxScheme")
    _text(tax_scheme2, "ID", "VAT", CBC_NS)

    monetary = ET.SubElement(root, f"{{{CAC_NS}}}LegalMonetaryTotal")
    _text(monetary, "LineExtensionAmount", f"{line_extension}", CBC_NS, currencyID=currency)
    _text(monetary, "TaxExclusiveAmount", f"{_q3(taxable)}", CBC_NS, currencyID=currency)
    _text(monetary, "TaxInclusiveAmount", f"{_q3(total)}", CBC_NS, currencyID=currency)
    _text(monetary, "PayableAmount", f"{_q3(total)}", CBC_NS, currencyID=currency)

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def tenant_for_sale(sale):
    """Resolve the Tenant row owning ``sale`` (each strategy needs the seller)."""
    from extensions import db
    from models import Tenant

    tenant_id = getattr(sale, "tenant_id", None)
    if tenant_id is None:
        return None
    return db.session.get(Tenant, int(tenant_id))


def invoice_sha256_hex(xml_payload: str) -> str:
    return hashlib.sha256(xml_payload.encode("utf-8")).hexdigest()


def zatca_document(sale, tenant, *, currency: str = "SAR") -> dict:
    """KSA simplified invoice: UBL 2.1 XML + TLV QR (tags 1-6)."""
    xml_payload = build_invoice_xml(
        sale, tenant, country="SA", currency=currency, profile_id="reporting", doc_type_code="388"
    )
    xml_sha256_b64 = base64.b64encode(hashlib.sha256(xml_payload.encode("utf-8")).digest()).decode("ascii")
    issue_dt = getattr(sale, "sale_date", None)
    timestamp = issue_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if issue_dt else ""
    tenant_name = (
        (
            (getattr(tenant, "name_en", None) or getattr(tenant, "name", None) or "").strip()
            or (getattr(tenant, "name_ar", None) or "").strip()
        )
        if tenant
        else ""
    )
    seller_id = (getattr(tenant, "tax_number", None) or "").strip() if tenant else ""
    total = Decimal(str(getattr(sale, "total_amount", 0) or 0))
    tax = Decimal(str(getattr(sale, "tax_amount", 0) or 0))
    qr = zatca_tlv_base64(tenant_name, seller_id, timestamp, total, tax, xml_sha256_b64)
    return {
        "xml_payload": xml_payload,
        "qr_base64": qr,
        "invoice_hash": invoice_sha256_hex(xml_payload),
        "format": "zatca_ubl_simplified_xml",
    }
