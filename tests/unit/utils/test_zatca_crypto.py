"""ZATCA Phase 2 — TLV and primitives, offline and self-contained."""

import base64
import datetime
import hashlib

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID

from utils.zatca_crypto import (
    ZATCA_INITIAL_PIH,
    ecdsa_sign_sha256,
    load_certificate_pem,
    load_private_key_pem,
    public_key_uncompressed_point_b64,
    sha256_b64,
    tlv_base64,
    verify_raw_signature,
)


@pytest.fixture(scope="module")
def test_material():
    """Self-signed P-256 material generated in-test — never used against ZATCA."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "local-test-ca"),
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
        .sign(key, __import__("cryptography").hazmat.primitives.hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem, key, cert


def _decode_tlv(payload_b64: str) -> dict[int, bytes]:
    raw = base64.b64decode(payload_b64)
    items = {}
    index = 0
    while index < len(raw):
        tag = raw[index]
        length = raw[index + 1]
        items[tag] = raw[index + 2 : index + 2 + length]
        index += 2 + length
    return items


def test_initial_pih_is_the_zatca_documented_zero_hash():
    # The ZATCA spec defines the first-in-chain PIH as base64(SHA256("0")).
    assert base64.b64decode(ZATCA_INITIAL_PIH) == hashlib.sha256(b"0").hexdigest().encode("ascii")


def test_tlv_round_trip_exact_fields():
    qr = tlv_base64([(1, b"Seller"), (2, b"300000000000003"), (4, b"1050.00")])
    assert _decode_tlv(qr) == {1: b"Seller", 2: b"300000000000003", 4: b"1050.00"}


def test_sha256_b64_is_32_bytes():
    assert len(base64.b64decode(sha256_b64(b"abc"))) == 32


def test_material_loads_and_signature_verifies(test_material):
    key_pem, cert_pem, _key, cert = test_material
    key = load_private_key_pem(key_pem)
    loaded_cert = load_certificate_pem(cert_pem)
    digest = hashlib.sha256(b"invoice").digest()

    raw_sig = ecdsa_sign_sha256(key, digest)
    assert len(raw_sig) == 64
    assert verify_raw_signature(loaded_cert.public_key(), digest, raw_sig)

    point = public_key_uncompressed_point_b64(loaded_cert)
    assert base64.b64decode(point)[0] == 0x04  # uncompressed-point marker
    assert cert.serial_number == loaded_cert.serial_number
