"""Coverage-99 boost for small models: pos_override_token, pos_printer,
document_verification, payment, card_payment."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


class TestPosOverrideToken:
    def test_expired_naive_and_repr(self):
        from models.pos_override_token import PosOverrideToken

        t = PosOverrideToken(
            action="void",
            cashier_user_id=1,
            supervisor_user_id=2,
            expires_at=datetime(2020, 1, 1),
        )
        assert t.is_expired() is True
        assert "void" in repr(t)
        assert "cashier=1" in repr(t)

    def test_not_expired_aware(self):
        from models.pos_override_token import PosOverrideToken

        t = PosOverrideToken(
            action="void",
            cashier_user_id=1,
            supervisor_user_id=2,
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        assert t.is_expired() is False


class TestPosPrinter:
    def test_for_tenant_filters(self, db_session, sample_tenant):
        from models.pos_printer import PosPrinter

        p1 = PosPrinter(tenant_id=sample_tenant.id, name="A", role="kitchen", is_active=True)
        p2 = PosPrinter(tenant_id=sample_tenant.id, name="B", role="customer", is_active=False)
        db_session.add_all([p1, p2])
        db_session.flush()
        assert len(PosPrinter.for_tenant(sample_tenant.id)) == 1
        assert len(PosPrinter.for_tenant(sample_tenant.id, active_only=False)) == 2
        assert len(PosPrinter.for_tenant(sample_tenant.id, role="kitchen")) == 1
        assert PosPrinter.for_tenant(sample_tenant.id, role="warehouse") == []

    def test_to_dict_and_helpers(self):
        from models.pos_printer import PosPrinter

        p = PosPrinter(name="K", role="kitchen", category_ids=[1, 2])
        assert p.categories == [1, 2]
        assert p.covers_category(1) is True
        assert p.covers_category(9) is False
        assert PosPrinter(name="X").covers_category(9) is True
        d = p.to_dict()
        assert d["name"] == "K"
        assert d["category_ids"] == [1, 2]
        serial = PosPrinter(connection_type="agent_serial", serial_port="COM1", baud_rate=None)
        assert serial.agent_printer_payload()["connection"] == "serial"
        net = PosPrinter(connection_type="agent_network", host=None, port=None, encoding=None)
        assert net.agent_printer_payload()["port"] == 9100


class TestDocumentVerification:
    def test_collision_then_success(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        existing = MagicMock()
        with (
            patch.object(DocumentVerification, "_generate_hash", return_value="h1"),
            patch.object(DocumentVerification, "query") as mq,
        ):
            mq.filter_by.return_value.first.side_effect = [None, existing, None]
            out = DocumentVerification.get_or_create(1, "sale", 5)
        assert out.document_hash == "h1"

    def test_ten_collisions_raise(self, db_session):
        from models.document_verification import DocumentVerification

        with (
            patch.object(DocumentVerification, "_generate_hash", return_value="h1"),
            patch.object(DocumentVerification, "query") as mq,
        ):
            mq.filter_by.return_value.first.side_effect = [None] + [MagicMock()] * 10
            try:
                DocumentVerification.get_or_create(1, "sale", 5)
                raised = False
            except RuntimeError:
                raised = True
            assert raised

    def test_existing_and_dict(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=77,
            document_hash="hx",
            public_token="tok",
        )
        db_session.add(rec)
        db_session.flush()
        found = DocumentVerification.get_or_create(sample_tenant.id, "sale", 77)
        assert found.id == rec.id
        assert found.to_dict()["document_hash"] == "hx"


class TestPaymentModel:
    def test_base_currency_display(self):
        from models.payment import Payment

        p = Payment()
        p.base_currency = "AED"
        assert p.base_currency_display == "AED"

    def test_validator_both_sources(self):
        from models.payment import Payment

        p = Payment()
        p.purchase_id = 2
        try:
            p.sale_id = 1
            raised = False
        except ValueError as e:
            raised = "at most one" in str(e)
        assert raised

    def test_validator_sale_outgoing(self):
        from models.payment import Payment

        p = Payment(direction="outgoing")
        try:
            p.sale_id = 1
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_validator_purchase_incoming(self):
        from models.payment import Payment

        p = Payment(direction="incoming")
        try:
            p.purchase_id = 2
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_confirm_already_confirmed(self):
        from models.payment import Payment

        p = Payment(payment_confirmed=True)
        p.confirm_payment()
        assert p.payment_confirmed is True

    def test_reject_unconfirmed(self):
        from models.payment import Payment

        p = Payment(payment_confirmed=False)
        p.reject_payment("nsf")
        assert p.payment_confirmed is False
        assert p.rejection_reason == "nsf"

    def test_status_direction(self):
        from models.payment import Payment

        assert Payment(payment_confirmed=True).status_ar == "مؤكدة"
        assert Payment(payment_confirmed=False).status_ar == "معلقة"
        assert Payment(payment_confirmed=False, rejection_reason="x").status_ar == "مرفوضة"
        assert Payment(direction="incoming").direction_ar == "وارد"
        assert Payment(direction="xx").direction_ar == "غير محدد"


class TestCardPayment:
    def test_stub_raises(self):
        from models.card_payment import _FernetStub

        try:
            _FernetStub(b"k")
            raised = False
        except RuntimeError:
            raised = True
        assert raised
        stub = _FernetStub.__new__(_FernetStub)
        for fn in ("encrypt", "decrypt"):
            try:
                getattr(stub, fn)(b"x")
                raised = False
            except RuntimeError:
                raised = True
            assert raised

    def test_encrypt_failure(self):
        from models.card_payment import CardPayment

        cp = CardPayment(customer_name="C")
        bad_cipher = MagicMock()
        bad_cipher.encrypt.side_effect = RuntimeError("bad key")
        assert cp.encrypt_card_data("4111111111111111", "123", "12/30", bad_cipher) is False

    def test_encrypt_types(self):
        from models.card_payment import CardPayment

        cp = CardPayment(customer_name="C")
        cipher = MagicMock()
        cipher.encrypt.side_effect = lambda b: b"enc:" + (b if isinstance(b, bytes) else b.encode())
        assert cp.encrypt_card_data("4111111111111111", "1", "e", cipher) is True
        assert cp.card_type == "Visa"
        assert cp.encrypt_card_data("5111111111111111", "1", "e", cipher) is True
        assert cp.card_type == "Mastercard"
        assert cp.encrypt_card_data("341111111111111", "1", "e", cipher) is True
        assert cp.card_type == "Amex"
        assert cp.encrypt_card_data("6011111111111111", "1", "e", cipher) is True
        assert cp.card_type == "Unknown"
        assert cp.encrypt_card_data("411", "1", "e", cipher) is True

    def test_decrypt_paths(self):
        from models.card_payment import CardPayment

        cp = CardPayment(customer_name="C")
        assert cp.decrypt_card_data() is None
        cp.encrypted_data = None
        assert cp.decrypt_card_data(MagicMock()) is None
        cipher = MagicMock()
        cipher.decrypt.side_effect = RuntimeError("bad")
        cp.encrypted_data = b"xx"
        assert cp.decrypt_card_data(cipher) is None

    def test_to_dict_with_cipher_no_decrypted(self):
        from models.card_payment import CardPayment

        cp = CardPayment(customer_name="C", amount=50, card_type="Visa", card_last_4="1111")
        d = cp.to_dict(cipher=MagicMock())
        assert "decrypted" not in d
        assert d["card_display"] == "Visa ****1111"
