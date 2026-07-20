"""CardPayment model — encryption, display helpers, stats queries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from models.card_payment import CardPayment


def _card_stub(**kwargs):
    class Stub:
        id = kwargs.get("id", 1)
        card_type = kwargs.get("card_type", "Visa")
        card_last_4 = kwargs.get("card_last_4", "4242")
        amount = kwargs.get("amount", Decimal("99.99"))
        customer_name = kwargs.get("customer_name", "Ali")
        customer_email = kwargs.get("customer_email", "ali@test.com")
        transaction_type = kwargs.get("transaction_type", "purchase")
        package = kwargs.get("package", "basic")
        status = kwargs.get("status", "completed")
        created_at = kwargs.get("created_at", datetime(2025, 6, 1, tzinfo=timezone.utc))
        encrypted_data = kwargs.get("encrypted_data")

        __repr__ = CardPayment.__repr__
        get_card_display = CardPayment.get_card_display
        encrypt_card_data = CardPayment.encrypt_card_data
        decrypt_card_data = CardPayment.decrypt_card_data
        to_dict = CardPayment.to_dict

    return Stub()


@pytest.fixture
def card_key(app):
    key = Fernet.generate_key().decode()
    app.config["CARD_ENCRYPTION_KEY"] = key
    app.config["ALLOW_CARD_DECRYPTION"] = True
    return key


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
        # Verify it's the real Fernet, not the stub
        assert cp.Fernet.__name__ == "Fernet"


class TestCardPaymentDisplay:
    def test_repr(self):
        assert "4242" in repr(_card_stub())

    def test_get_card_display_with_type(self):
        assert _card_stub().get_card_display() == "Visa ****4242"

    def test_get_card_display_without_type(self):
        assert _card_stub(card_type=None).get_card_display() == "Card ****4242"


class TestCardPaymentCrypto:
    def test_encrypt_decrypt_roundtrip(self, app, card_key):
        with app.app_context():
            cp = CardPayment()
            assert cp.encrypt_card_data("4111111111111111", "123", "12/28") is True
            assert cp.card_type == "Visa"
            assert cp.card_last_4 == "1111"
            assert cp.card_bin == "411111"
            decrypted = cp.decrypt_card_data()
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
    def test_card_type_detection(self, app, card_key, number, card_type):
        with app.app_context():
            cp = CardPayment()
            cp.encrypt_card_data(number, "999", "01/30")
            assert cp.card_type == card_type

    def test_short_card_number(self, app, card_key):
        with app.app_context():
            cp = CardPayment()
            cp.encrypt_card_data("123", "1", "01/30")
            assert cp.card_last_4 == "123"
            assert cp.card_bin is None

    def test_encrypt_returns_false_on_cipher_error(self, app):
        with app.app_context():
            app.config["CARD_ENCRYPTION_KEY"] = ""
            cp = CardPayment()
            assert cp.encrypt_card_data("4111111111111111", "123", "12/28") is False

    def test_encrypt_returns_false_on_exception(self, app, card_key, mocker):
        with app.app_context():
            mocker.patch.object(CardPayment, "_encrypt", side_effect=RuntimeError("fail"))
            cp = CardPayment()
            assert cp.encrypt_card_data("4111111111111111", "123", "12/28") is False

    def test_decrypt_blocked_when_flag_off(self, app, card_key):
        with app.app_context():
            cp = CardPayment()
            cp.encrypt_card_data("4111111111111111", "123", "12/28")
            app.config["ALLOW_CARD_DECRYPTION"] = False
            assert cp.decrypt_card_data() is None

    def test_decrypt_without_encrypted_data(self, app, card_key):
        with app.app_context():
            assert CardPayment().decrypt_card_data() is None

    def test_decrypt_corrupt_payload_returns_none(self, app, card_key):
        with app.app_context():
            cp = CardPayment()
            cp.encrypted_data = b"not-valid-fernet"
            assert cp.decrypt_card_data() is None

    def test_static_encrypt_decrypt_helpers(self, app, card_key):
        with app.app_context():
            assert CardPayment._encrypt(None) is None
            assert CardPayment._decrypt(None) is None
            blob = CardPayment._encrypt("secret")
            assert CardPayment._decrypt(blob) == "secret"
            assert CardPayment._encrypt(b"bytes") is not None

    def test_get_cipher_bytes_key(self, app):
        with app.app_context():
            app.config["CARD_ENCRYPTION_KEY"] = Fernet.generate_key()
            cipher = CardPayment._get_cipher()
            assert cipher is not None

    def test_get_cipher_missing_key_raises(self, app):
        with app.app_context():
            app.config["CARD_ENCRYPTION_KEY"] = ""
            with pytest.raises(ValueError, match="CARD_ENCRYPTION_KEY"):
                CardPayment._get_cipher()

    def test_get_cipher_without_crypto_raises(self, app, monkeypatch):
        monkeypatch.setattr("models.card_payment.HAS_CRYPTO", False)
        with app.app_context():
            with pytest.raises(RuntimeError, match="cryptography"):
                CardPayment._get_cipher()


class TestCardPaymentToDict:
    def test_to_dict_null_created_at(self, app):
        with app.app_context():
            stub = _card_stub(created_at=None)
            data = stub.to_dict()
            assert data["created_at"] is None

    def test_to_dict_basic(self, app):
        with app.app_context():
            data = _card_stub(amount=None).to_dict()
            assert data["amount"] == 0
            assert data["created_at"] is not None

    def test_to_dict_with_decryption(self, app, card_key):
        with app.app_context():
            cp = CardPayment(
                customer_name="N",
                transaction_type="donation",
                amount=Decimal("10"),
            )
            cp.encrypt_card_data("4111111111111111", "123", "12/28")
            data = cp.to_dict(include_encrypted=True)
            assert "decrypted" in data

    def test_to_dict_skips_decryption_when_disabled(self, app, card_key):
        with app.app_context():
            cp = CardPayment(
                customer_name="N",
                transaction_type="donation",
                amount=Decimal("10"),
            )
            cp.encrypt_card_data("4111111111111111", "123", "12/28")
            app.config["ALLOW_CARD_DECRYPTION"] = False
            assert "decrypted" not in cp.to_dict(include_encrypted=True)


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
