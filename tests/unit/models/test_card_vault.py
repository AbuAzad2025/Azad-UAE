from __future__ import annotations

import pytest

from services.card_encryption_service import CardEncryptionService


@pytest.fixture
def cipher():
    return CardEncryptionService(encryption_key="vault-test-key-12345")


class TestCardEncryptionService:
    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="CARD_ENCRYPTION_KEY"):
            CardEncryptionService(encryption_key="")

    def test_encrypt_decrypt_roundtrip(self, cipher):
        enc = cipher.encrypt("4111111111111111")
        assert cipher.decrypt(enc) == "4111111111111111"

    def test_encrypt_none_returns_none(self, cipher):
        assert cipher.encrypt("") is None
        assert cipher.decrypt(b"") is None

    def test_hash_card(self):
        h = CardEncryptionService.hash_card("4111-1111-1111-1111")
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
        assert CardEncryptionService.detect_card_type(number) == expected


class TestCardVaultInstance:
    @staticmethod
    def _vault(cipher):
        from models.card_vault import CardVault

        v = CardVault()
        v.set_card_data("4111-1111-1111-1111", "John Doe", "12", "2028", "123", cipher=cipher)
        return v

    def test_set_card_data(self, cipher):
        v = self._vault(cipher)
        assert v.last_four == "1111"
        assert v.card_type == "visa"
        assert v.card_hash

    def test_set_card_data_requires_cipher(self):
        from models.card_vault import CardVault

        v = CardVault()
        with pytest.raises(ValueError, match="cipher is required"):
            v.set_card_data("4111111111111111", "John")

    def test_get_cardholder_name(self, cipher):
        v = self._vault(cipher)
        assert v.get_cardholder_name(cipher) == "John Doe"

    def test_get_cardholder_name_no_cipher(self, cipher):
        v = self._vault(cipher)
        assert v.get_cardholder_name() is None

    def test_get_expiry(self, cipher):
        v = self._vault(cipher)
        assert v.get_expiry(cipher) == "12/2028"

    def test_get_expiry_none_when_missing(self, cipher):
        from models.card_vault import CardVault

        v = CardVault()
        v.set_card_data("4111111111111111", "Jane", cipher=cipher)
        assert v.get_expiry(cipher) is None

    def test_get_card_number_masked_without_cipher(self, cipher):
        v = self._vault(cipher)
        assert v.get_card_number().startswith("****")

    def test_get_card_number_with_cipher(self, cipher):
        v = self._vault(cipher)
        num = v.get_card_number(cipher)
        assert num.startswith("4111-")

    def test_get_cvv_no_encrypted_value(self, cipher):
        from models.card_vault import CardVault

        v = CardVault()
        v.set_card_data("4111111111111111", "Jane", cipher=cipher)
        v.cvv_encrypted = None
        assert v.get_cvv(cipher) is None

    def test_get_cvv_masked_without_cipher(self, cipher):
        v = self._vault(cipher)
        assert v.get_cvv() is None

    def test_get_cvv_with_cipher(self, cipher):
        v = self._vault(cipher)
        assert v.get_cvv(cipher) == "123"

    def test_mark_used(self, cipher):
        v = self._vault(cipher)
        v.usage_count = 0
        v.mark_used()
        assert v.usage_count == 1
        assert v.last_used is not None

    def test_to_dict_without_cipher(self, cipher):
        v = self._vault(cipher)
        v.id = 1
        v.customer_id = 5
        v.is_default = True
        data = v.to_dict()
        assert data["last_four"] == "1111"
        assert "card_number" not in data

    def test_to_dict_with_cipher(self, cipher):
        v = self._vault(cipher)
        v.id = 1
        v.customer_id = 5
        data = v.to_dict(cipher)
        assert "card_number" in data
        assert "cvv" in data

    def test_repr(self, cipher):
        v = self._vault(cipher)
        assert "1111" in repr(v)
