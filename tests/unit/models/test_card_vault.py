from __future__ import annotations

import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet


def _fernet_key(raw="test-card-key"):
    key_bytes = raw.encode() if isinstance(raw, str) else raw
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest()))


class TestCardVaultCrypto:
    def test_get_cipher_missing_key(self, app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = ""
        with app.app_context():
            with pytest.raises(ValueError, match="CARD_ENCRYPTION_KEY"):
                CardVault._get_cipher()

    def test_encrypt_decrypt_roundtrip(self, app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = "vault-test-key-12345"
        with app.app_context():
            enc = CardVault._encrypt("4111111111111111")
            assert CardVault._decrypt(enc) == "4111111111111111"

    def test_encrypt_none_returns_none(self, app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = "vault-test-key-12345"
        with app.app_context():
            assert CardVault._encrypt(None) is None
            assert CardVault._decrypt(None) is None

    def test_hash_card(self):
        from models.card_vault import CardVault

        h = CardVault._hash_card("4111-1111-1111-1111")
        assert len(h) == 64

    @pytest.mark.parametrize(
        "number,expected",
        [
            ("4111111111111111", "visa"),
            ("5511111111111111", "mastercard"),
            ("371111111111111", "amex"),
            ("6011111111111111", "discover"),
            ("9999111111111111", "unknown"),
        ],
    )
    def test_detect_card_type(self, number, expected):
        from models.card_vault import CardVault

        assert CardVault._detect_card_type(number) == expected

    def test_no_crypto_raises(self, app):
        from models import card_vault as cv_mod

        with patch.object(cv_mod, "HAS_CRYPTO", False):
            with app.app_context():
                app.config["CARD_ENCRYPTION_KEY"] = "key"
                with pytest.raises(RuntimeError, match="cryptography"):
                    cv_mod.CardVault._get_cipher()


class TestCardVaultInstance:
    @staticmethod
    def _vault(app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = "vault-test-key-12345"
        with app.app_context():
            v = CardVault()
            v.set_card_data("4111-1111-1111-1111", "John Doe", "12", "2028", "123")
            return v

    def test_set_card_data(self, app):
        v = self._vault(app)
        assert v.last_four == "1111"
        assert v.card_type == "visa"
        assert v.card_hash

    def test_get_cardholder_name(self, app):
        v = self._vault(app)
        with app.app_context():
            assert v.get_cardholder_name() == "John Doe"

    def test_get_expiry(self, app):
        v = self._vault(app)
        with app.app_context():
            assert v.get_expiry() == "12/2028"

    def test_get_expiry_none_when_missing(self, app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = "vault-test-key-12345"
        with app.app_context():
            v = CardVault()
            v.set_card_data("4111111111111111", "Jane")
            assert v.get_expiry() is None

    def test_get_card_number_masked(self, app):
        v = self._vault(app)
        app.config["ALLOW_CARD_DECRYPTION"] = False
        with app.app_context():
            assert v.get_card_number().startswith("****")

    def test_get_card_number_owner_decrypt(self, app):
        v = self._vault(app)
        app.config["ALLOW_CARD_DECRYPTION"] = True
        owner = MagicMock(is_owner=True)
        with app.app_context(), patch("flask_login.current_user", owner):
            num = v.get_card_number()
            assert num.startswith("4111-")

    def test_get_card_number_non_owner_with_decryption_allowed(self, app):
        v = self._vault(app)
        app.config["ALLOW_CARD_DECRYPTION"] = True
        with (
            app.app_context(),
            patch("flask_login.current_user", MagicMock(is_owner=False)),
        ):
            assert v.get_card_number().startswith("****")

    def test_get_cvv_no_encrypted_value(self, app):
        from models.card_vault import CardVault

        app.config["CARD_ENCRYPTION_KEY"] = "vault-test-key-12345"
        app.config["ALLOW_CARD_DECRYPTION"] = True
        with app.app_context():
            v = CardVault()
            v.set_card_data("4111111111111111", "Jane")
            v.cvv_encrypted = None
            with patch("flask_login.current_user", MagicMock(is_owner=True)):
                assert v.get_cvv() is None

    def test_get_cvv_masked_when_decryption_disabled(self, app):
        v = self._vault(app)
        app.config["ALLOW_CARD_DECRYPTION"] = False
        with app.app_context():
            assert v.get_cvv() == "***"
        v = self._vault(app)
        app.config["ALLOW_CARD_DECRYPTION"] = True
        with (
            app.app_context(),
            patch("flask_login.current_user", MagicMock(is_owner=False)),
        ):
            assert v.get_cvv() == "***"
        with (
            app.app_context(),
            patch("flask_login.current_user", MagicMock(is_owner=True)),
        ):
            assert v.get_cvv() == "123"

    def test_mark_used(self, app):
        v = self._vault(app)
        v.usage_count = 0
        v.mark_used()
        assert v.usage_count == 1
        assert v.last_used is not None

    def test_to_dict(self, app):
        v = self._vault(app)
        v.id = 1
        v.customer_id = 5
        v.is_default = True
        with app.app_context():
            data = v.to_dict()
        assert data["last_four"] == "1111"
        assert "card_number" not in data

    def test_to_dict_sensitive_owner(self, app):
        v = self._vault(app)
        v.id = 1
        v.customer_id = 5
        app.config["ALLOW_CARD_DECRYPTION"] = True
        with (
            app.app_context(),
            patch("flask_login.current_user", MagicMock(is_owner=True)),
        ):
            data = v.to_dict(include_sensitive=True)
        assert "card_number" in data

    def test_repr(self, app):
        v = self._vault(app)
        assert "1111" in repr(v)
