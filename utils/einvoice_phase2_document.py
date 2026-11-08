"""ZATCA Phase 2 invoice document builder — simplified tax invoices & notes.

Produces the fully signed document: the invoice XML with an enveloped
``ds:Signature`` inside ``ext:UBLExtensions`` (DigestValue over the invoice
with the extension removed, XML-DSig enveloped-signature semantics), the
Invoice Counter Value (ICV) and Previous Invoice Hash (PIH) as
``AdditionalDocumentReference`` blocks, and the ZATCA TLV QR (tags 1–9).

The tenant's CSID (certificate + private key) comes from ZATCA onboarding and
is read from the tenant's encrypted secrets — nothing here fabricates it.
"""

from __future__ import annotations

import base64
from decimal import ROUND_HALF_UP, Decimal

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from lxml import etree

from utils.zatca_crypto import (
    ZATCA_INITIAL_PIH,
    ecdsa_sign_sha256,
    load_certificate_pem,
    load_private_key_pem,
    public_key_uncompressed_point_b64,
    sha256_b64,
    sha256_hex,
    tlv_base64,
)

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
    "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
C14N_METHOD = "http://www.w3.org/2006/12/xml-c14n11"
SIGNATURE_METHOD = "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"
DIGEST_METHOD = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED_TRANSFORM = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"


def _q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _sub(parent, tag, text=None, ns="cbc", **attrib):
    element = etree.SubElement(parent, f"{{{NS[ns]}}}{tag}", **{k: str(v) for k, v in attrib.items()})
    if text is not None:
        element.text = str(text)
    return element


def _iso_date_time(sale):
    issue = getattr(sale, "sale_date", None)
    if issue is None:
        return "", "00:00:00Z"
    return issue.strftime("%Y-%m-%d"), issue.strftime("%H:%M:%SZ")


def build_signed_invoice_xml(
    sale,
    tenant,
    *,
    icv: int,
    previous_pih: str,
    csid_private_key_pem: str,
    csid_certificate_pem: str,
    doc_type: str = "invoice",
    currency: str = "SAR",
    billing_reference: str | None = None,
):
    """Build, sign and serialize a ZATCA Phase 2 simplified invoice.

    Returns ``{"xml_payload": str, "invoice_hash": hex, "qr_base64": str,
    "invoice_counter_value": int, "previous_invoice_hash": str}``.
    """
    tenant_name = (
        (getattr(tenant, "name_en", None) or "").strip()
        or (getattr(tenant, "name", None) or "").strip()
        or (getattr(tenant, "name_ar", None) or "").strip()
    )
    seller_id = (getattr(tenant, "tax_number", None) or "").strip()
    customer = getattr(sale, "customer", None)
    buyer_name = (getattr(customer, "name", None) or "").strip() if customer else ""
    buyer_id = (getattr(customer, "tax_number", None) or "").strip() if customer else ""
    issue_date, issue_time = _iso_date_time(sale)

    rate = Decimal(str(getattr(sale, "tax_rate", 0) or 0))
    total = _q3(getattr(sale, "total_amount", 0))
    tax_amount = _q3(getattr(sale, "tax_amount", 0))
    taxable = _q3(getattr(sale, "taxable_amount", 0) or (total - tax_amount))
    line_extension = _q3(
        getattr(sale, "subtotal", 0)
        or sum((Decimal(str(getattr(ln, "line_total", 0) or 0)) for ln in getattr(sale, "lines", [])), Decimal("0"))
    )
    is_credit = doc_type == "credit_note"
    invoice_type_code = "381" if is_credit else "388"

    # ------------------------------------------------------------------
    # Stage 1 — the unsigned invoice (no UBLExtensions, no QR reference).
    # ------------------------------------------------------------------
    root = etree.Element(
        f"{{{UBL_NS}}}Invoice",
        nsmap={
            "cbc": NS["cbc"],
            "cac": NS["cac"],
            "ext": NS["ext"],
            "sig": NS["sig"],
            "sac": NS["sac"],
            "ds": NS["ds"],
        },
    )
    _sub(root, "ProfileID", "reporting:1.0")
    _sub(root, "ID", getattr(sale, "sale_number", ""))
    _sub(root, "UUID", _invoice_uuid(sale))
    _sub(root, "IssueDate", issue_date)
    _sub(root, "IssueTime", issue_time)
    _sub(root, "InvoiceTypeCode", invoice_type_code, name="0200000")
    _sub(root, "DocumentCurrencyCode", currency)
    _sub(root, "TaxCurrencyCode", currency)

    icv_ref = _sub(root, "AdditionalDocumentReference", ns="cac")
    _sub(icv_ref, "ID", "ICV")
    _sub(icv_ref, "UUID", str(icv))
    icv_att = _sub(icv_ref, "Attachment", ns="cac")
    _sub(icv_att, "EmbeddedDocumentBinaryObject", str(icv), mimeCode="text/plain")

    pih_ref = _sub(root, "AdditionalDocumentReference", ns="cac")
    _sub(pih_ref, "ID", "PIH")
    _sub(pih_ref, "UUID", _pih_uuid(sale))
    pih_att = _sub(pih_ref, "Attachment", ns="cac")
    _sub(pih_att, "EmbeddedDocumentBinaryObject", previous_pih or ZATCA_INITIAL_PIH, mimeCode="text/plain")

    if billing_reference:
        billing_ref = _sub(root, "BillingReference", ns="cac")
        adoc = _sub(billing_ref, "AdditionalDocumentReference", ns="cac")
        _sub(adoc, "ID", billing_reference)

    supplier = _sub(root, "AccountingSupplierParty", ns="cac")
    party = _sub(supplier, "Party", ns="cac")
    party_id = _sub(party, "PartyIdentification", ns="cac")
    _sub(party_id, "ID", seller_id or "000000000000000", schemeID="CRN")
    party_name = _sub(party, "PartyName", ns="cac")
    _sub(party_name, "Name", tenant_name)
    address = _sub(party, "PostalAddress", ns="cac")
    _sub(
        address,
        "StreetName",
        (getattr(tenant, "address_en", None) or getattr(tenant, "address_ar", None) or "").strip(),
    )
    _sub(address, "CityName", (getattr(tenant, "city", None) or "").strip())
    country = _sub(address, "Country", ns="cac")
    _sub(country, "IdentificationCode", "SA")
    tax_scheme = _sub(party, "PartyTaxScheme", ns="cac")
    _sub(tax_scheme, "CompanyID", seller_id or "000000000000000")
    scheme = _sub(tax_scheme, "TaxScheme", ns="cac")
    _sub(scheme, "ID", "VAT")

    buyer = _sub(root, "AccountingCustomerParty", ns="cac")
    buyer_party = _sub(buyer, "Party", ns="cac")
    buyer_name_el = _sub(buyer_party, "PartyName", ns="cac")
    _sub(buyer_name_el, "Name", buyer_name or "Walk-in Customer")
    buyer_addr = _sub(buyer_party, "PostalAddress", ns="cac")
    buyer_country = _sub(buyer_addr, "Country", ns="cac")
    _sub(buyer_country, "IdentificationCode", "SA")
    buyer_legal = _sub(buyer_party, "PartyLegalEntity", ns="cac")
    _sub(buyer_legal, "RegistrationName", buyer_name or "Walk-in Customer")
    if buyer_id:
        buyer_tax = _sub(buyer_party, "PartyTaxScheme", ns="cac")
        _sub(buyer_tax, "CompanyID", buyer_id)
        buyer_scheme = _sub(buyer_tax, "TaxScheme", ns="cac")
        _sub(buyer_scheme, "ID", "VAT")

    for index, line in enumerate(getattr(sale, "lines", []) or [], start=1):
        product = getattr(line, "product", None)
        name = (getattr(product, "name", None) or f"Item {getattr(line, 'product_id', index)}").strip()
        invoice_line = _sub(root, "InvoiceLine", ns="cac")
        _sub(invoice_line, "ID", str(index))
        _sub(invoice_line, "InvoicedQuantity", f"{_q3(getattr(line, 'quantity', 0))}", unitCode="PCE")
        _sub(invoice_line, "LineExtensionAmount", f"{_q3(getattr(line, 'line_total', 0))}", currencyID=currency)
        item = _sub(invoice_line, "Item", ns="cac")
        _sub(item, "Name", name)
        category_id = getattr(line, "tax_category", "standard") or "standard"
        classified = etree.SubElement(item, f"{{{NS['cac']}}}ClassifiedTaxCategory")
        _sub(classified, "ID", "Z" if category_id == "zero" else ("E" if category_id == "exempt" else "S"))
        _sub(classified, "Percent", "0" if category_id != "standard" else f"{rate}")
        tax_scheme2 = _sub(classified, "TaxScheme", ns="cac")
        _sub(tax_scheme2, "ID", "VAT")
        price = _sub(invoice_line, "Price", ns="cac")
        _sub(price, "PriceAmount", f"{_q3(getattr(line, 'unit_price', 0))}", currencyID=currency)

    tax_total = _sub(root, "TaxTotal", ns="cac")
    _sub(tax_total, "TaxAmount", f"{_q3(tax_amount)}", currencyID=currency)
    subtotal = _sub(tax_total, "TaxSubtotal", ns="cac")
    _sub(subtotal, "TaxableAmount", f"{_q3(taxable)}", currencyID=currency)
    _sub(subtotal, "TaxAmount", f"{_q3(tax_amount)}", currencyID=currency)
    category = _sub(subtotal, "TaxCategory", ns="cac")
    _sub(category, "ID", "S")
    _sub(category, "Percent", f"{rate}")
    tax_scheme3 = _sub(category, "TaxScheme", ns="cac")
    _sub(tax_scheme3, "ID", "VAT")

    monetary = _sub(root, "LegalMonetaryTotal", ns="cac")
    _sub(monetary, "LineExtensionAmount", f"{line_extension}", currencyID=currency)
    _sub(monetary, "TaxExclusiveAmount", f"{_q3(taxable)}", currencyID=currency)
    _sub(monetary, "TaxInclusiveAmount", f"{_q3(total)}", currencyID=currency)
    _sub(monetary, "PayableAmount", f"{_q3(total)}", currencyID=currency)

    stage1_bytes = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)

    # ------------------------------------------------------------------
    # Stage 2 — assemble the enveloped signature, then sign the canonical
    # form of the SignedInfo exactly as it lives in the document.
    # ------------------------------------------------------------------
    digest_b64 = sha256_b64(stage1_bytes)

    ubl_extensions = etree.Element(f"{{{NS['ext']}}}UBLExtensions")
    extension = etree.SubElement(ubl_extensions, f"{{{NS['ext']}}}UBLExtension")
    _sub(extension, "ExtensionURI", ns="ext").text = "urn:oasis:names:specification:ubl:dsig:enveloped:xades"
    content = etree.SubElement(extension, f"{{{NS['ext']}}}ExtensionContent")
    signatures = etree.SubElement(
        content,
        f"{{{NS['sig']}}}UBLDocumentSignatures",
        nsmap={"sac": NS["sac"]},
    )
    sig_info = etree.SubElement(signatures, f"{{{NS['sac']}}}SignatureInformation")
    signature = etree.SubElement(sig_info, f"{{{NS['ds']}}}Signature", Id="Signature")
    signed_info = etree.SubElement(signature, f"{{{NS['ds']}}}SignedInfo")
    _sub(signed_info, "CanonicalizationMethod", ns="ds", Algorithm=C14N_METHOD)
    _sub(signed_info, "SignatureMethod", ns="ds", Algorithm=SIGNATURE_METHOD)
    reference = _sub(signed_info, "Reference", ns="ds", URI="")
    transforms = _sub(reference, "Transforms", ns="ds")
    _sub(transforms, "Transform", ns="ds", Algorithm=ENVELOPED_TRANSFORM)
    _sub(reference, "DigestMethod", ns="ds", Algorithm=DIGEST_METHOD)
    _sub(reference, "DigestValue", digest_b64, ns="ds")
    signature_value_el = _sub(signature, "SignatureValue", "", ns="ds")
    key_info = etree.SubElement(signature, f"{{{NS['ds']}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{NS['ds']}}}X509Data")
    cert_der = x509.load_pem_x509_certificates(csid_certificate_pem.encode("utf-8"))[0].public_bytes(
        serialization.Encoding.DER
    )
    cert_b64 = base64.b64encode(cert_der).decode("ascii")
    _sub(x509_data, "X509Certificate", cert_b64, ns="ds")

    root.insert(0, ubl_extensions)
    final_bytes = etree.tostring(root, xml_declaration=False, encoding="UTF-8")

    embedded_signed_info = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignedInfo")
    signed_info_c14n = etree.tostring(embedded_signed_info, method="c14n", exclusive=False, with_comments=False)
    private_key = load_private_key_pem(csid_private_key_pem)
    certificate = load_certificate_pem(csid_certificate_pem)
    signature_raw = ecdsa_sign_sha256(private_key, signed_info_c14n)
    signature_b64 = base64.b64encode(signature_raw).decode("ascii")
    signature_value_el.text = signature_b64

    final_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    # ------------------------------------------------------------------
    # QR — TLV tags 1–9 (base64 of the concatenated tuples).
    # ------------------------------------------------------------------
    timestamp = issue_date + "T" + (issue_time or "00:00:00Z")
    tag9 = _certificate_ca_signature_b64(certificate)
    qr_b64 = tlv_base64(
        [
            (1, tenant_name.encode("utf-8")),
            (2, seller_id.encode("utf-8")),
            (3, timestamp.encode("utf-8")),
            (4, str(_q2(total)).encode("utf-8")),
            (5, str(_q2(tax_amount)).encode("utf-8")),
            (6, base64.b64decode(digest_b64)),
            (7, signature_raw),
            (8, base64.b64decode(public_key_uncompressed_point_b64(certificate))),
            (9, tag9),
        ]
    )

    return {
        "xml_payload": final_bytes.decode("utf-8"),
        "invoice_hash": sha256_hex(stage1_bytes),
        "qr_base64": qr_b64,
        "invoice_counter_value": icv,
        "format": "zatca_phase2_simplified_xml",
    }


def _certificate_ca_signature_b64(certificate) -> bytes:
    """QR tag 9 — the CA's signature on the stamp certificate (raw bytes)."""
    return certificate.signature


def _invoice_uuid(sale) -> str:
    import uuid

    return str(uuid.uuid4())


def _pih_uuid(sale) -> str:
    import uuid

    return str(uuid.uuid4())
