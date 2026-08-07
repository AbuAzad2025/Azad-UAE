"""CardPayment model — display helpers, stats queries, and cipher-based encryption."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.card_payment import CardPayment
from services.card_encryption_service import CardEncryptionService


@pytest.fixture
def cipher(app):
    return CardEncryptionService(encryption_key="test-encryption-key-32-chars-long!!")


class TestCardPaymentImportFallback:
    def test_fernet_stub_raises_on_instantiation(self):
        from models.card_payment import _FernetStub

        stub = _FernetStub
        assert stub is not None
        with pytest.raises(RuntimeError, match="cryptography module not installed"):
            stub(b"test-key")

    def test_module_level_import_succeeded(self):
        import models.card_payment as cp

        assert cp.HAS_CRYPTO is True
        assert callable(cp.Fernet)


class TestCardPaymentDisplay:
    def test_repr(self):
        cp = CardPayment(
            card_type="Visa",
            card_last_4="4242",
            amount=Decimal("99.99"),
        )
        assert "4242" in repr(cp)

    def test_get_card_display_with_type(self):
        cp = CardPayment(card_type="Visa", card_last_4="4242", amount=Decimal("99.99"))
        assert cp.get_card_display() == "Visa ****4242"

    def test_get_card_display_without_type(self):
        cp = CardPayment(card_type=None, card_last_4="4242", amount=Decimal("99.99"))
        assert cp.get_card_display() == "Card ****4242"


class TestCardPaymentCrypto:
    def test_encrypt_decrypt_roundtrip(self, cipher):
        cp = CardPayment()
        assert cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=cipher) is True
        assert cp.card_type == "Visa"
        assert cp.card_last_4 == "1111"
        assert cp.card_bin == "411111"
        decrypted = cp.decrypt_card_data(cipher)
        assert decrypted is not None
        assert decrypted["card_number"] == "4111111111111111"
        assert decrypted["cvv"] == "123"
        assert "****1111" in decrypted["display"]

    @pytest.mark.parametrize(
        "number,card_type",
        [
            ("5111111111111111", "Mastercard"),
            ("5211111111111111", "Mastercard"),
            ("341111111111111", "Amex"),
            ("371111111111111", "Amex"),
            ("6011111111111111", "Unknown"),
        ],
    )
    def test_card_type_detection(self, cipher, number, card_type):
        cp = CardPayment()
        cp.encrypt_card_data(number, "999", "01/30", cipher=cipher)
        assert cp.card_type == card_type

    def test_short_card_number(self, cipher):
        cp = CardPayment()
        cp.encrypt_card_data("123", "1", "01/30", cipher=cipher)
        assert cp.card_last_4 == "123"
        assert cp.card_bin is None

    def test_encrypt_requires_cipher(self):
        cp = CardPayment()
        with pytest.raises(ValueError, match="cipher is required"):
            cp.encrypt_card_data("4111111111111111", "123", "12/28")

    def test_decrypt_without_cipher_returns_none(self, cipher):
        cp = CardPayment()
        cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=cipher)
        assert cp.decrypt_card_data() is None

    def test_decrypt_without_encrypted_data(self, cipher):
        assert CardPayment().decrypt_card_data(cipher) is None

    def test_decrypt_corrupt_payload_returns_none(self, cipher):
        cp = CardPayment()
        cp.encrypted_data = b"not-valid-fernet"
        assert cp.decrypt_card_data(cipher) is None


class TestCardPaymentToDict:
    def test_to_dict_null_created_at(self):
        cp = CardPayment(
            card_type="Visa",
            card_last_4="4242",
            amount=Decimal("99.99"),
            created_at=None,
        )
        data = cp.to_dict()
        assert data["created_at"] is None

    def test_to_dict_basic(self):
        cp = CardPayment(
            card_type="Visa",
            card_last_4="4242",
            amount=None,
            created_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        data = cp.to_dict()
        assert data["amount"] == 0
        assert data["created_at"] is not None

    def test_to_dict_with_cipher(self, cipher):
        cp = CardPayment(
            customer_name="N",
            transaction_type="donation",
            amount=Decimal("10"),
        )
        cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=cipher)
        data = cp.to_dict(cipher)
        assert "decrypted" in data

    def test_to_dict_without_cipher(self, cipher):
        cp = CardPayment(
            customer_name="N",
            transaction_type="donation",
            amount=Decimal("10"),
        )
        cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=cipher)
        assert "decrypted" not in cp.to_dict()


class TestCardPaymentStats:
    def test_get_total_card_payments(self, mocker):
        q = MagicMock()
        q.filter_by.return_value.scalar.return_value = Decimal("1500.50")
        mocker.patch("models.card_payment.db.session.query", return_value=q)
        assert CardPayment.get_total_card_payments() == 1500.50

    def test_get_total_card_payments_empty(self, mocker):
        q = MagicMock()
        q.filter_by.return_value.scalar.return_value = None
        mocker.patch("models.card_payment.db.session.query", return_value=q)
        assert CardPayment.get_total_card_payments() == 0

    def test_get_card_stats(self, mocker):
        row = SimpleNamespace(card_type="Visa", count=3, total=Decimal("300"))
        q = MagicMock()
        q.filter_by.return_value.group_by.return_value.all.return_value = [row]
        mocker.patch("models.card_payment.db.session.query", return_value=q)
        stats = CardPayment.get_card_stats()
        assert stats[0]["type"] == "Visa"
        assert stats[0]["count"] == 3
        assert stats[0]["total"] == 300.0

    def test_get_card_stats_null_total(self, mocker):
        row = SimpleNamespace(card_type="Amex", count=1, total=None)
        q = MagicMock()
        q.filter_by.return_value.group_by.return_value.all.return_value = [row]
        mocker.patch("models.card_payment.db.session.query", return_value=q)
        stats = CardPayment.get_card_stats()
        assert stats[0]["total"] == 0
