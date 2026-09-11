"""Gap coverage for models/card_payment.py — failure paths + real-DB stats."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from models.card_payment import CardPayment, _FernetStub
from services.card_encryption_service import CardEncryptionService


@pytest.fixture
def cipher(app):
    return CardEncryptionService(encryption_key="test-encryption-key-32-chars-long!!")


def _payment(tenant_id, **kwargs):
    params = {
        "tenant_id": tenant_id,
        "customer_name": kwargs.get("customer_name", "Test Customer"),
        "transaction_type": kwargs.get("transaction_type", "purchase"),
        "amount": kwargs.get("amount", Decimal("25.50")),
        "status": kwargs.get("status", "completed"),
        "card_type": kwargs.get("card_type", "Visa"),
    }
    return CardPayment(**params)


class TestFernetStubFailures:
    def test_stub_encrypt_raises(self):
        stub = _FernetStub.__new__(_FernetStub)
        with pytest.raises(RuntimeError, match="cryptography module not installed"):
            stub.encrypt(b"data")

    def test_stub_decrypt_raises(self):
        stub = _FernetStub.__new__(_FernetStub)
        with pytest.raises(RuntimeError, match="cryptography module not installed"):
            stub.decrypt(b"token")


class TestEncryptFailurePath:
    def test_encrypt_exception_returns_false(self):
        class _Boom:
            def encrypt(self, payload):
                raise ValueError("boom")

        cp = CardPayment()
        assert cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=_Boom()) is False
        assert cp.encrypted_data is None


class TestDecryptFailurePaths:
    def test_decrypt_bad_json_returns_none(self):
        class _BadJson:
            def decrypt(self, token):
                return "not-json{{{"

        cp = CardPayment()
        cp.encrypted_data = b"something"
        assert cp.decrypt_card_data(_BadJson()) is None

    def test_decrypt_cipher_raises_returns_none(self, cipher):
        cp = CardPayment()
        cp.encrypt_card_data("4111111111111111", "123", "12/28", cipher=cipher)

        class _Boom:
            def decrypt(self, token):
                raise RuntimeError("boom")

        assert cp.decrypt_card_data(_Boom()) is None

    def test_decrypt_missing_key_returns_none(self, cipher):
        class _Partial:
            def decrypt(self, token):
                return "{}"

        cp = CardPayment(card_type="Visa", card_last_4="1111")
        cp.encrypted_data = b"x"
        data = cp.decrypt_card_data(_Partial())
        assert data is not None
        assert data["card_number"] is None


class TestToDictCipherNoData:
    def test_to_dict_with_cipher_but_no_payload(self, cipher):
        cp = CardPayment(
            customer_name="N",
            transaction_type="donation",
            amount=Decimal("10"),
            created_at=datetime.now(UTC),
        )
        data = cp.to_dict(cipher)
        assert "decrypted" not in data


class TestRealDbStats:
    def test_total_card_payments_real_db(self, db_session, sample_tenant):
        db_session.add(_payment(sample_tenant.id, amount=Decimal("100")))
        db_session.add(_payment(sample_tenant.id, amount=Decimal("50"), status="pending"))
        db_session.flush()
        total = CardPayment.get_total_card_payments()
        assert total >= 100

    def test_total_card_payments_empty_table(self, db_session):
        db_session.query(CardPayment).delete()
        db_session.flush()
        assert CardPayment.get_total_card_payments() == 0

    def test_card_stats_real_db(self, db_session, sample_tenant):
        db_session.add(_payment(sample_tenant.id, amount=Decimal("30"), card_type="Visa"))
        db_session.add(_payment(sample_tenant.id, amount=Decimal("20"), card_type="Amex"))
        db_session.flush()
        stats = CardPayment.get_card_stats()
        by_type = {row["type"]: row for row in stats}
        assert by_type["Visa"]["count"] >= 1
        assert by_type["Visa"]["total"] >= 30

    def test_card_stats_empty_table(self, db_session):
        db_session.query(CardPayment).delete()
        db_session.flush()
        assert CardPayment.get_card_stats() == []
