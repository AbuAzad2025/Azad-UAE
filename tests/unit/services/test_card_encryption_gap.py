"""Gap coverage: CardEncryptionService roundtrips, edge inputs, card typing."""

from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet, InvalidToken

from services.card_encryption_service import CardEncryptionService


class TestInit:
    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="CARD_ENCRYPTION_KEY"):
            CardEncryptionService("")

    def test_none_key_raises(self):
        with pytest.raises(ValueError):
            CardEncryptionService(None)

    def test_string_key_accepted(self):
        svc = CardEncryptionService("unit-test-key")
        assert svc._cipher is not None

    def test_bytes_key_accepted(self):
        svc = CardEncryptionService(b"raw-bytes-key")
        assert svc._cipher is not None

    def test_key_derivation_is_sha256_b64(self):
        derived = base64.urlsafe_b64encode(hashlib.sha256(b"k").digest())
        svc_a = CardEncryptionService("k")
        payload = b"same plaintext"
        token = svc_a.encrypt(payload)
        assert Fernet(derived).decrypt(token) == payload


class TestEncryptDecryptRoundtrip:
    @pytest.mark.parametrize(
        "plaintext",
        [
            "4111111111111111",
            "مريم أحمد | 5555-4444-3333-2222",
            "x",
            " ",
        ],
    )
    def test_roundtrip_str(self, plaintext):
        svc = CardEncryptionService("k")
        token = svc.encrypt(plaintext)
        assert isinstance(token, bytes)
        assert token != plaintext.encode()
        assert svc.decrypt(token) == plaintext

    def test_roundtrip_bytes_payload(self):
        svc = CardEncryptionService("k")
        blob = b"\x00\x01binary-ish"
        token = svc.encrypt(blob)
        assert svc.decrypt(token).encode() == blob

    def test_encrypt_empty_str_returns_none(self):
        assert CardEncryptionService("k").encrypt("") is None

    def test_encrypt_none_returns_none(self):
        assert CardEncryptionService("k").encrypt(None) is None

    def test_decrypt_empty_returns_none(self):
        assert CardEncryptionService("k").decrypt(b"") is None

    def test_wrong_key_raises_invalid_token(self):
        enc = CardEncryptionService("key-A")
        dec = CardEncryptionService("key-B")
        with pytest.raises(InvalidToken):
            dec.decrypt(enc.encrypt("4111111111111111"))

    def test_fernet_tokens_are_unique_per_call(self):
        svc = CardEncryptionService("k")
        a = svc.encrypt("4242424242424242")
        b = svc.encrypt("4242424242424242")
        assert a != b


class TestHashCard:
    def test_deterministic_sha256_hex(self):
        expected = hashlib.sha256(b"4111111111111111").hexdigest()
        assert CardEncryptionService.hash_card("4111111111111111") == expected

    def test_output_is_64_hex_chars(self):
        digest = CardEncryptionService.hash_card("5555444433332222")
        assert len(digest) == 64
        int(digest, 16)

    def test_distinct_numbers_hash_differently(self):
        assert CardEncryptionService.hash_card("1") != CardEncryptionService.hash_card("2")


class TestDetectCardType:
    @pytest.mark.parametrize(
        ("number", "expected"),
        [
            ("4111111111111111", "visa"),
            ("4000 0000 0000 0002", "visa"),
            ("5123-4567-8901-2345", "mastercard"),
            ("5500005555555559", "mastercard"),
            ("5300000000000006", "mastercard"),
            ("340000000000009", "amex"),
            ("371449635398431", "amex"),
            ("6011111111111117", "discover"),
            ("6221261111111111", "discover"),
            ("1234567890123456", "unknown"),
            ("98765", "unknown"),
        ],
    )
    def test_detection(self, number, expected):
        assert CardEncryptionService.detect_card_type(number) == expected

    def test_detection_handles_non_string_input(self):
        assert CardEncryptionService.detect_card_type(4111111111111111) == "visa"
