"""ZATCA Phase 2 cryptographic primitives — pure, testable, offline.

What this module implements (per the ZATCA detailed technical guideline):

* TLV assembly for the QR code (tags 1–9), base64 of the concatenated tuples.
* The invoice hash: SHA-256 over the invoice *before* any signature material
  is embedded — equivalent to removing the signature/PIH/QR blocks and
  canonicalizing, because the pre-sign document has none of those nodes.
* ECDSA P-256 signing of the hash (the CSID is issued by ZATCA at
  onboarding; this code never generates or invents a CSID).
* The fixed "zeroth" PIH for the first invoice in the chain.

What it does NOT do: onboarding with ZATCA (CSR, PCSID exchange, compliance
checks) or submitting invoices to FATOORA. Both need the tenant's ZATCA
credentials; neither can be done or verified offline.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

# base64(SHA256(b"0")) — the previous-invoice hash for the first invoice.
ZATCA_INITIAL_PIH = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def tlv_base64(fields: list[tuple[int, bytes]]) -> str:
    """Assemble a TLV byte array and return its base64 encoding."""
    payload = b"".join(bytes([tag, len(value)]) + value for tag, value in fields)
    return base64.b64encode(payload).decode("ascii")


def ecdsa_sign_sha256(private_key: ec.EllipticCurvePrivateKey, digest: bytes) -> bytes:
    """ECDSA P-256 signature over a 32-byte digest — raw r||s form (64 bytes)."""
    der = private_key.sign(digest, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_raw_signature(public_key: ec.EllipticCurvePublicKey, digest: bytes, raw_signature: bytes) -> bool:
    """Verify a raw r||s ECDSA signature (used by tests)."""
    half = len(raw_signature) // 2
    r = int.from_bytes(raw_signature[:half], "big")
    s = int.from_bytes(raw_signature[half:], "big")
    try:
        public_key.verify(encode_dss_signature(r, s), digest, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def load_private_key_pem(pem: str) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("ZATCA private key must be an elliptic-curve key")
    return key


def load_certificate_pem(pem: str):
    certs = x509.load_pem_x509_certificates(pem.encode("utf-8"))
    if not certs:
        raise ValueError("No certificate found in the provided PEM")
    return certs[0]


def public_key_uncompressed_point_b64(cert) -> str:
    """QR tag 8 — the certificate's EC public key as uncompressed point bytes."""
    point = cert.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return base64.b64encode(point).decode("ascii")
