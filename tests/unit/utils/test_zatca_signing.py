"""ZATCA enveloped signing — real cryptography, locally verifiable.

Signs with generated keys and verifies back; tampering and wrong keys must
fail. This proves the local artifact is genuinely signed — it does not
prove FATOORA acceptance (no live authority call here).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from utils.zatca_signing import sign_xml, verify_xml

XML = "<Invoice><ID>INV-1</ID><Total>118.00</Total></Invoice>"


def _ec_keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return private_pem, public_pem


def _rsa_keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return private_pem, public_pem


class TestEnvelopedSigning:
    def test_ec_sign_verify_roundtrip(self):
        private_pem, public_pem = _ec_keypair()
        signed = sign_xml(XML, private_pem)
        assert "<ds:Signature" in signed
        assert verify_xml(signed, public_pem) is True

    def test_rsa_sign_verify_roundtrip(self):
        private_pem, public_pem = _rsa_keypair()
        signed = sign_xml(XML, private_pem)
        assert "<ds:Signature" in signed
        assert verify_xml(signed, public_pem) is True

    def test_tampered_document_fails_verification(self):
        private_pem, public_pem = _ec_keypair()
        signed = sign_xml(XML, private_pem)
        tampered = signed.replace("<Total>118.00</Total>", "<Total>999.00</Total>")
        assert verify_xml(tampered, public_pem) is False

    def test_wrong_key_fails_verification(self):
        private_pem, _ = _ec_keypair()
        _, other_public = _ec_keypair()
        signed = sign_xml(XML, private_pem)
        assert verify_xml(signed, other_public) is False

    def test_unsigned_document_fails_verification(self):
        _, public_pem = _ec_keypair()
        assert verify_xml(XML, public_pem) is False

    def test_unparseable_key_raises(self):
        import pytest

        with pytest.raises(ValueError, match="parseable PEM"):
            sign_xml(XML, "not-a-key")
