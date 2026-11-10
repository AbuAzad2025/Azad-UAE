"""Enveloped XML signing for ZATCA FATOORA reporting payloads.

The stored e-invoice artifact is an unsigned UBL document. FATOORA
reporting expects a *signed* invoice, so this module produces an enveloped
``ds:Signature`` (SHA-256 digest + RSA/ECDSA signature, keyed by the
tenant's CSID private key) and can verify it back. Full FATOORA
canonicalization (C14N) and the live round-trip still require the
authority's sandbox — this utility makes the local artifact genuinely
signed and tamper-evident rather than claiming government acceptance.
"""

from __future__ import annotations

import base64
import hashlib
import re

_SIGNATURE_RE = re.compile(r"<ds:Signature.*?</ds:Signature>", re.DOTALL)


def _digest(xml: str) -> bytes:
    return hashlib.sha256(xml.encode("utf-8")).digest()


def sign_xml(xml_payload: str, private_key_pem: str, certificate_pem: str = "") -> str:
    """Return ``xml_payload`` with an enveloped ds:Signature appended.

    Raises ValueError when the private key cannot be parsed — callers must
    not silently submit an unsigned document as if it were signed.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    try:
        private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    except Exception as exc:
        raise ValueError("ZATCA private key is not a parseable PEM key.") from exc

    digest_b64 = base64.b64encode(_digest(xml_payload)).decode("ascii")

    if isinstance(private_key, rsa.RSAPrivateKey):
        signature = private_key.sign(
            _digest(xml_payload),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        alg = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

        der = private_key.sign(_digest(xml_payload), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = encode_dss_signature(r, s)
        alg = "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"
    else:
        raise ValueError(f"Unsupported ZATCA key type: {type(private_key).__name__}")

    signature_b64 = base64.b64encode(signature).decode("ascii")
    cert_block = ""
    if certificate_pem:
        cert_block = (
            "<ds:KeyInfo><ds:X509Data><ds:X509Certificate>"
            + "".join(
                line.strip()
                for line in certificate_pem.splitlines()
                if line.strip() and "BEGIN" not in line and "END" not in line
            )
            + "</ds:X509Certificate></ds:X509Data></ds:KeyInfo>"
        )
    signed_info = (
        "<ds:SignedInfo>"
        '<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        '<ds:SignatureMethod Algorithm="' + alg + '"/>'
        '<ds:Reference URI="">'
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
        f"<ds:DigestValue>{digest_b64}</ds:DigestValue>"
        "</ds:Reference>"
        "</ds:SignedInfo>"
    )
    signature_xml = (
        '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        + signed_info
        + f"<ds:SignatureValue>{signature_b64}</ds:SignatureValue>"
        + cert_block
        + "</ds:Signature>"
    )
    if "</Invoice>" in xml_payload:
        return xml_payload.replace("</Invoice>", signature_xml + "</Invoice>", 1)
    return xml_payload + signature_xml


def verify_xml(xml_payload: str, public_key_pem: str | None = None) -> bool:
    """Verify the enveloped signature against the embedded digest.

    Without an explicit public key, verification uses the key embedded in
    the document's KeyInfo when present; otherwise it returns False.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    match = _SIGNATURE_RE.search(xml_payload)
    if not match:
        return False
    signature_xml = match.group(0)
    unsigned = xml_payload.replace(signature_xml, "", 1)

    digest_match = re.search(r"<ds:DigestValue>([^<]+)</ds:DigestValue>", signature_xml)
    value_match = re.search(r"<ds:SignatureValue>([^<]+)</ds:SignatureValue>", signature_xml)
    if not digest_match or not value_match:
        return False
    try:
        expected_digest = base64.b64decode(digest_match.group(1))
        signature = base64.b64decode(value_match.group(1))
    except Exception:
        return False
    if _digest(unsigned) != expected_digest:
        return False

    if public_key_pem is None:
        cert_match = re.search(r"<ds:X509Certificate>([^<]+)</ds:X509Certificate>", signature_xml)
        if not cert_match:
            return False
        from cryptography import x509

        pem = (
            "-----BEGIN CERTIFICATE-----\n"
            + "\n".join(cert_match.group(1)[i : i + 64] for i in range(0, len(cert_match.group(1)), 64))
            + "\n-----END CERTIFICATE-----"
        )
        try:
            public_key = x509.load_pem_x509_certificate(pem.encode("utf-8")).public_key()
        except Exception:
            return False
    else:
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        except Exception:
            return False

    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, _digest(unsigned), padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, _digest(unsigned), ec.ECDSA(hashes.SHA256()))
        else:
            return False
    except InvalidSignature:
        return False
    return True
