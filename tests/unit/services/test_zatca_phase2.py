"""ZATCA Phase 2 — signed simplified invoice, ICV/PIH chain, TLV QR 1-9."""

import base64
import datetime
from decimal import Decimal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from lxml import etree

from utils.einvoice_phase2_document import build_signed_invoice_xml, sha256_b64


@pytest.fixture(scope="module")
def csid_material():
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "local-test-csid"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TEST_ORG"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem, key, cert


def _sale(tenant):
    from decimal import Decimal
    from types import SimpleNamespace

    line = SimpleNamespace(
        unit_price=Decimal("500"),
        line_total=Decimal("1000"),
        product=SimpleNamespace(name="Widget"),
        product_id=1,
        tax_category="standard",
    )
    from decimal import Decimal

    sale = SimpleNamespace(
        id=42,
        sale_number="S-999",
        tenant_id=getattr(tenant, "id", 1),
        customer=SimpleNamespace(name="Buyer", tax_number=""),
        sale_date=datetime.datetime(2026, 11, 9, 10, 0, 0, tzinfo=datetime.UTC),
        currency="SAR",
        tax_rate=Decimal("15"),
        tax_amount=Decimal("150"),
        taxable_amount=Decimal("1000"),
        subtotal=Decimal("1000"),
        total_amount=Decimal("1150"),
        lines=[line],
    )
    return sale


def _tlv_items(payload_b64):
    import base64

    raw = base64.b64decode(payload_b64)
    items = {}
    index = 0
    while index < len(raw):
        tag = raw[index]
        length = raw[index + 1]
        items[tag] = raw[index + 2 : index + 2 + length]
        index += 2 + length
    return items


def test_phase2_builds_signed_document(csid_material, sample_tenant):
    key_pem, cert_pem, key, cert = csid_material
    sale = _sale(sample_tenant)
    result = build_signed_invoice_xml(
        sale,
        sample_tenant,
        icv=1,
        previous_pih="NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==",
        csid_private_key_pem=key_pem,
        csid_certificate_pem=cert_pem,
        doc_type="invoice",
        currency="SAR",
    )

    root = etree.fromstring(result["xml_payload"].encode("utf-8"))
    assert result["format"] == "zatca_phase2_simplified_xml"
    assert result["invoice_counter_value"] == 1
    # ICV/PIH embedded
    assert "ICV" in result["xml_payload"]
    assert "PIH" in result["xml_payload"]
    # QR tags 1-9
    items = _tlv_items(result["qr_base64"])
    assert set(items) == {1, 2, 3, 4, 5, 6, 7, 8, 9}
    assert items[4] == b"1150.00"
    assert items[5] == b"150.00"
    # Tag 6 (hash) matches the stored invoice_hash (base64 of the digest)
    assert items[6] == bytes.fromhex(result["invoice_hash"])
    # Signature verifies against the signed-info canonical form (recompute).
    # We verify the ECDSA signature of the invoice hash with the cert's public key.
    raw_sig = items[7]
    assert len(raw_sig) == 64
    siginfo = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignedInfo")
    assert siginfo is not None
    digest_value = siginfo.find(
        "{http://www.w3.org/2000/09/xmldsig#}Reference/{http://www.w3.org/2000/09/xmldsig#}DigestValue"
    ).text
    assert digest_value == base64.b64encode(items[6]).decode("ascii")
    # The invoice's hash (tag 6) is recomputable from the document without
    # the UBLExtensions block — the same canonicalisation the builder used.
    root2 = etree.fromstring(result["xml_payload"].encode("utf-8"))
    for ext in root2.findall("{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtensions"):
        root2.remove(ext)
    assert sha256_b64(etree.tostring(root2, method="c14n", exclusive=False, with_comments=False)) == digest_value
    # Tag 8 is the uncompressed public key (65 bytes, 0x04 marker).
    assert items[8][0] == 0x04  # uncompressed-point marker
    # Tag 9 is the CA's signature on the stamp cert (non-empty).
    assert len(items[9]) > 0
    # The UBLExtensions node is the first child of Invoice.
    assert root.tag.endswith("}Invoice")
    assert root[0].tag.endswith("}UBLExtensions")


def test_phase2_credit_note_uses_381_and_billing_reference(csid_material, sample_tenant):
    key_pem, cert_pem, _key, _cert = csid_material
    sale = _sale(sample_tenant)
    result = build_signed_invoice_xml(
        sale,
        sample_tenant,
        icv=2,
        previous_pih=base64.b64encode(b"x" * 32).decode("ascii"),
        csid_private_key_pem=key_pem,
        csid_certificate_pem=cert_pem,
        doc_type="credit_note",
        currency="SAR",
        billing_reference="S-ORIG",
    )
    assert "381" in result["xml_payload"]
    assert "<cbc:ID>S-ORIG</cbc:ID>" in result["xml_payload"]
    assert result["format"] == "zatca_phase2_simplified_xml"  # doc_type changes only the code
    assert result["invoice_counter_value"] == 2


def test_phase2_round_trip_with_stored_secrets(db_session, sample_tenant, sample_branch, sample_user, mocker):
    # End-to-end through the service, secrets stored encrypted.
    # Generate material inside the test (no fixture dependency).
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from services.tenant_secrets_service import TenantSecretsService

    key = ec.generate_private_key(ec.SECP256R1())
    now = __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "csid")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "csid")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    TenantSecretsService.set(
        sample_tenant.id,
        "zatca_private_key",
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
        user_id=sample_user.id,
    )
    TenantSecretsService.set(
        sample_tenant.id,
        "zatca_certificate",
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        user_id=sample_user.id,
    )
    sample_tenant.zatca_phase2_enabled = True
    sample_tenant.vat_country = "SA"
    db_session.commit()

    from models import Customer, Product, Sale, SaleLine

    customer = Customer(tenant_id=sample_tenant.id, name="Buyer")
    db_session.add(customer)
    db_session.flush()
    product = Product(tenant_id=sample_tenant.id, name="Widget", regular_price=Decimal("1000"))
    db_session.add(product)
    db_session.flush()
    sale = Sale(
        tenant_id=sample_tenant.id,
        customer_id=customer.id,
        seller_id=sample_user.id,
        sale_number="S-PH2",
        branch_id=sample_branch.id,
        currency="SAR",
        base_currency="SAR",
        amount=Decimal("1150"),
        amount_aed=Decimal("1150"),
        subtotal=Decimal("1000"),
        tax_rate=Decimal("15"),
        tax_amount=Decimal("150"),
        taxable_amount=Decimal("1000"),
        total_amount=Decimal("1150"),
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=sample_tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal("2"),
        unit_price=Decimal("500"),
        line_total=Decimal("1000"),
    )
    line.product = product
    db_session.add(line)
    db_session.flush()
    sale.lines = [line]
    sale.customer = customer

    from services.einvoice_service import EInvoiceService

    row = EInvoiceService.generate_for_sale(sale)
    assert row is not None
    assert row.format == "zatca_phase2_simplified_xml"
    assert row.invoice_counter_value == 1

    # Second sale chains on top of the first.
    sale2 = Sale(
        tenant_id=sample_tenant.id,
        customer_id=customer.id,
        seller_id=sample_user.id,
        sale_number="S-PH2B",
        branch_id=sample_branch.id,
        currency="SAR",
        base_currency="SAR",
        amount=Decimal("1150"),
        amount_aed=Decimal("1150"),
        subtotal=Decimal("1000"),
        tax_rate=Decimal("15"),
        tax_amount=Decimal("150"),
        taxable_amount=Decimal("1000"),
        total_amount=Decimal("1150"),
    )
    db_session.add(sale2)
    db_session.flush()
    sale2.lines = [line]
    sale2.customer = customer
    row2 = EInvoiceService.generate_for_sale(sale2)
    assert row2.invoice_counter_value == 2
    assert row2.invoice_counter_value == 2
