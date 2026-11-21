"""Branch-level coverage for four utils modules whose error paths are rarely hit.

Everything here is offline: the signing tests use locally generated keys and a
self-signed certificate, the reconciler tests use a canned SQLAlchemy
``Connection`` stand-in, and the transaction-safety tests patch the scoped
session. No production code is modified and no external service is contacted.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID
from sqlalchemy.exc import OperationalError

from utils.balance_reconciliation import _base, _customer_expected, _d, _supplier_expected, reconcile
from utils.db_safety import lock_row_for_update, release_session
from utils.localization.israel import IsraelStrategy
from utils.zatca_signing import sign_xml, verify_xml

_XML = "<Invoice><ID>INV-GAP</ID><Total>118.00</Total></Invoice>"


# ─── IsraelStrategy ──────────────────────────────────────────────────────


class TestIsraelStrategyGaps:
    def test_resolve_rate_prefers_explicit_rate(self):
        strategy = IsraelStrategy()
        assert strategy._resolve_vat_rate(tax_rate=Decimal("7")) == Decimal("7")
        result = strategy.calculate_tax(Decimal("100.00"), tax_rate=Decimal("18"))
        assert result == {
            "tax_amount": Decimal("18.00"),
            "net_amount": Decimal("100.00"),
            "total_amount": Decimal("118.00"),
            "rate_applied": Decimal("18"),
        }

    def test_resolve_rate_uses_sale_rate_then_defaults(self):
        strategy = IsraelStrategy()
        assert strategy._resolve_vat_rate(sale=SimpleNamespace(tax_rate=Decimal("9"))) == Decimal("9")
        assert strategy._resolve_vat_rate(sale=SimpleNamespace()) == strategy.default_vat_rate
        assert strategy._resolve_vat_rate() == strategy.default_vat_rate
        assert strategy.calculate_tax(Decimal("100"))["rate_applied"] == strategy.default_vat_rate

    def test_zero_rate_is_not_taxed(self):
        result = IsraelStrategy().calculate_tax(Decimal("77.77"), tax_rate=Decimal("0"))
        assert result == {
            "tax_amount": Decimal("0"),
            "net_amount": Decimal("77.77"),
            "total_amount": Decimal("77.77"),
            "rate_applied": Decimal("0"),
        }

    def test_sale_total_walks_every_supported_attribute(self):
        total = IsraelStrategy._sale_total
        assert total(SimpleNamespace(total_aed=Decimal("11"))) == Decimal("11")
        assert total(SimpleNamespace(amount_aed=Decimal("12"))) == Decimal("12")
        assert total(SimpleNamespace(total_amount=Decimal("13"))) == Decimal("13")
        assert total(SimpleNamespace(amount=Decimal("14"))) == Decimal("14")
        assert total(SimpleNamespace()) == Decimal("0")

    def test_tax_return_subtracts_input_vat(self):
        report = IsraelStrategy().format_tax_return(Decimal("200"), Decimal("50"), "2026-01-01", "2026-03-31")
        assert report["net_payable"] == Decimal("150")
        assert report["format"] == "il_vat_v1"
        assert report["currency"] == "ILS"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, False), ("", False), ("123", False), ("123456789", True), ("123-45-6789", True)],
    )
    def test_validate_tax_number(self, value, expected):
        assert IsraelStrategy().validate_tax_number(value) is expected


# ─── db_safety ───────────────────────────────────────────────────────────


class _RowModel:
    __name__ = "RowModel"
    id: Any = sa.column("id")


def _configure_query(mock_db, first_result):
    """Wire the chained query mocks used by lock_row_for_update."""
    query = mock_db.session.query.return_value
    filtered = query.filter.return_value
    filtered.populate_existing.return_value = filtered
    for node in (query, filtered):
        first = node.with_for_update.return_value.first
        if isinstance(first_result, (list, BaseException)):
            first.side_effect = first_result
        else:
            first.return_value = first_result
    return filtered


def _lock_error(code="40P01"):
    error = OperationalError("SELECT 1", {}, Exception("deadlock detected"))
    error.pgcode = code
    return error


class TestLockRowForUpdateGaps:
    def test_missing_row_raises_lookup_error_and_rolls_back_savepoint(self):
        with patch("utils.db_safety.db") as mock_db:
            _configure_query(mock_db, None)
            with pytest.raises(LookupError, match="RowModel\\(7\\) not found"):
                lock_row_for_update(_RowModel, 7)
            mock_db.session.begin_nested.return_value.rollback.assert_called_once()

    def test_non_lock_error_is_reraised_immediately(self):
        with patch("utils.db_safety.db") as mock_db:
            _configure_query(mock_db, OperationalError("SELECT 1", {}, Exception("connection reset")))
            with pytest.raises(OperationalError):
                lock_row_for_update(_RowModel, 8)
            mock_db.session.begin_nested.return_value.rollback.assert_called_once()

    def test_final_lock_attempt_is_logged_critical(self):
        with (
            patch("utils.db_safety.db") as mock_db,
            patch("utils.db_safety._MAX_LOCK_RETRIES", 1),
            patch("utils.db_safety.logger") as logger,
        ):
            _configure_query(mock_db, _lock_error("55P03"))
            with pytest.raises(OperationalError):
                lock_row_for_update(_RowModel, 9)
            logger.critical.assert_called_once()
            logger.warning.assert_not_called()

    def test_lock_contention_retries_with_backoff_then_succeeds(self):
        sentinel = object()
        with (
            patch("utils.db_safety.db") as mock_db,
            patch("utils.db_safety._MAX_LOCK_RETRIES", 2),
            patch("utils.db_safety.time.sleep") as sleep,
            patch("utils.db_safety.random.uniform", return_value=0.0),
            patch("utils.db_safety.logger") as logger,
        ):
            _configure_query(mock_db, [_lock_error(), sentinel])
            assert lock_row_for_update(_RowModel, 10) is sentinel
            sleep.assert_called_once_with(0.02)
            logger.warning.assert_called_once()

    def test_populate_existing_false_skips_refresh(self):
        with patch("utils.db_safety.db") as mock_db:
            filtered = _configure_query(mock_db, object())
            assert lock_row_for_update(_RowModel, 11, populate_existing=False) is not None
            filtered.populate_existing.assert_not_called()


class TestReleaseSessionGaps:
    def test_active_transaction_is_ended(self):
        with patch("utils.db_safety.db") as mock_db:
            session = mock_db.session.return_value
            session.in_transaction.return_value = True
            assert release_session("probe") is True
            session.rollback.assert_called_once()

    def test_inspection_failure_returns_false(self):
        with patch("utils.db_safety.db") as mock_db, patch("utils.db_safety.logger") as logger:
            mock_db.session.return_value.in_transaction.side_effect = RuntimeError("connection gone")
            assert release_session("probe") is False
            logger.error.assert_called_once()


# ─── balance_reconciliation ──────────────────────────────────────────────


def _row(**fields):
    return SimpleNamespace(**fields)


class _FakeResult:
    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeConn:
    """Dispatch on compiled SQL so the reconciler can be driven without a DB."""

    def __init__(self, data):
        self.data = data
        self.executed = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append(sql)
        data = self.data
        if "COALESCE(SUM(l.debit" in sql:
            account = (params or {}).get("a")
            return _FakeResult(scalar=data["gl_balances"].get(account, 0))
        if sql.startswith("UPDATE "):
            return _FakeResult()
        if "customers.id, customers.balance" in sql:
            return _FakeResult(data["customers_select"])
        if sql == "SELECT id FROM customers":
            return _FakeResult(data["customers"])
        if "FROM sales" in sql:
            return _FakeResult(data["sales"])
        if "FROM payments" in sql:
            key = "payments_customer" if "customer_id IS NOT NULL" in sql else "payments_supplier"
            return _FakeResult(data[key])
        if "FROM receipts" in sql:
            return _FakeResult(data["receipts"])
        if "FROM product_returns" in sql:
            return _FakeResult(data["product_returns"])
        if "FROM maintenance_orders" in sql:
            return _FakeResult(data["maintenance_orders"])
        if "FROM maintenance_invoices" in sql:
            return _FakeResult(data["maintenance_invoices"])
        if "FROM maintenance_receipts" in sql:
            return _FakeResult(data["maintenance_receipts"])
        if "FROM maintenance_returns" in sql:
            return _FakeResult(data["maintenance_returns"])
        if "suppliers.id, suppliers.total_purchases_aed" in sql:
            return _FakeResult(data["suppliers_select"])
        if sql == "SELECT id FROM suppliers":
            return _FakeResult(data["suppliers"])
        if "FROM purchase_returns" in sql:
            return _FakeResult(data["purchase_returns"])
        if "FROM purchases" in sql:
            return _FakeResult(data["purchases"])
        if "FROM maintenance_purchase_orders" in sql:
            return _FakeResult(data["mpqs"])
        if "SELECT partners.id" in sql:
            return _FakeResult(data["partners"])
        if "FROM partner_transactions" in sql:
            return _FakeResult(data["partner_txns"])
        if "cash_boxes.id" in sql:
            return _FakeResult(data["cash_boxes"])
        if "FROM tenants" in sql:
            return _FakeResult(data["tenants"])
        raise AssertionError(f"Unexpected SQL: {sql!r}")


def _reconciliation_data():
    """Include orphan rows and live effects to walk every 'skip' and 'effect' branch."""
    return {
        "tenants": [_row(id=1, base_currency="AED", default_currency=None)],
        "customers": [_row(id=10), _row(id=11)],
        "customers_select": [
            _row(id=10, balance=Decimal("0"), total_purchases=Decimal("0")),
            _row(id=11, balance=Decimal("0"), total_purchases=Decimal("0")),
        ],
        "sales": [
            _row(customer_id=10, amount_aed=Decimal("100")),
            _row(customer_id=999, amount_aed=Decimal("500")),
        ],
        "payments_customer": [
            _row(
                customer_id=10,
                direction="incoming",
                amount_aed=Decimal("40"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
                reference_number="REF-1",
            ),
            _row(
                customer_id=888,
                direction="incoming",
                amount_aed=Decimal("5"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
                reference_number=None,
            ),
        ],
        "receipts": [
            _row(
                customer_id=10,
                receipt_number="REF-1",
                amount_aed=Decimal("10"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
            ),
            _row(
                customer_id=777,
                receipt_number="X",
                amount_aed=Decimal("3"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
            ),
        ],
        "product_returns": [
            _row(customer_id=10, amount_aed=Decimal("20")),
            _row(customer_id=666, amount_aed=Decimal("30")),
        ],
        "maintenance_orders": [
            _row(
                id=50,
                customer_id=10,
                tenant_id=1,
                currency="USD",
                exchange_rate=Decimal("3.5"),
                base_currency="AED",
            )
        ],
        "maintenance_invoices": [
            _row(order_id=50, amount_aed=Decimal("30")),
            _row(order_id=999, amount_aed=Decimal("1")),
        ],
        "maintenance_receipts": [
            _row(order_id=50, amount=Decimal("10"), is_refund=False),
            _row(order_id=999, amount=Decimal("1"), is_refund=True),
        ],
        "maintenance_returns": [
            _row(order_id=50, total_value_aed=Decimal("7")),
            _row(order_id=999, total_value_aed=Decimal("9")),
        ],
        "suppliers": [_row(id=20), _row(id=21)],
        "suppliers_select": [
            _row(id=20, total_purchases_aed=Decimal("0"), total_paid_aed=Decimal("0")),
            _row(id=21, total_purchases_aed=Decimal("0"), total_paid_aed=Decimal("0")),
        ],
        "purchases": [
            _row(supplier_id=20, amount_aed=Decimal("200")),
            _row(supplier_id=555, amount_aed=Decimal("9")),
        ],
        "purchase_returns": [
            _row(supplier_id=20, amount_aed=Decimal("5")),
            _row(supplier_id=444, amount_aed=Decimal("3")),
        ],
        "payments_supplier": [
            _row(
                supplier_id=20,
                direction="outgoing",
                amount_aed=Decimal("50"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
            ),
            _row(
                supplier_id=333,
                direction="outgoing",
                amount_aed=Decimal("5"),
                payment_confirmed=True,
                payment_method="cash",
                rejection_reason=None,
            ),
        ],
        "mpqs": [
            _row(
                supplier_id=20,
                tenant_id=1,
                total_amount=Decimal("100"),
                currency="EUR",
                exchange_rate=Decimal("2"),
            ),
            _row(
                supplier_id=222,
                tenant_id=1,
                total_amount=Decimal("10"),
                currency="EUR",
                exchange_rate=Decimal("2"),
            ),
        ],
        "partners": [_row(id=30, current_balance=Decimal("0"))],
        "partner_txns": [_row(id=300, amount_base=Decimal("10"), balance_after=Decimal("10"))],
        "cash_boxes": [
            _row(id=40, gl_account_id=None, current_balance=Decimal("5")),
            _row(id=41, gl_account_id=99, current_balance=Decimal("0")),
            _row(id=42, gl_account_id=98, current_balance=Decimal("999")),
        ],
        "gl_balances": {99: Decimal("0"), 98: Decimal("10")},
    }


class TestBalanceReconciliationGaps:
    def test_helpers_cover_orphans_and_currency_conversion(self):
        conn = _FakeConn(_reconciliation_data())
        tenant_base = {1: "AED"}
        customers = _customer_expected(conn, tenant_base)
        purchases, paid = _supplier_expected(conn, tenant_base)

        # -100 sale +40 payment +20 return -30 invoice +35 FX receipt +7 return = -28
        assert customers[10] == Decimal("-28.000")
        assert purchases[20] == Decimal("395.000")
        assert paid[20] == Decimal("50.000")
        assert _d("not-a-number") == Decimal("0")
        assert _d(None) == Decimal("0")
        assert _base(Decimal("10"), "USD", Decimal("2"), "AED") == Decimal("20.000")

    def test_reconcile_cash_box_skip_and_no_discrepancy_branches(self):
        conn = _FakeConn(_reconciliation_data())
        preview = reconcile(conn, apply=False)
        assert [box["id"] for box in preview["cash_boxes"]] == [42]
        assert 40 not in [box["id"] for box in preview["cash_boxes"]]
        assert 41 not in [box["id"] for box in preview["cash_boxes"]]

        applied = reconcile(conn, apply=True)
        assert applied["applied"] is True
        assert any("UPDATE cash_boxes" in sql for sql in conn.executed)


# ─── zatca_signing ───────────────────────────────────────────────────────


def _material():
    """Self-signed P-256 material generated in-test — never used against ZATCA."""
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-zatca-gap-test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


class TestZatcaSigningGaps:
    def test_certificate_is_embedded_and_verify_uses_keyinfo(self):
        private_pem, _, cert_pem = _material()
        signed = sign_xml(_XML, private_pem, certificate_pem=cert_pem)
        assert "<ds:X509Certificate>" in signed
        assert verify_xml(signed) is True

    def test_signature_is_appended_without_invoice_closing_tag(self):
        private_pem, public_pem, _ = _material()
        payload = "<Invoice><ID>INV-GAP</ID>"
        signed = sign_xml(payload, private_pem)
        assert signed.startswith(payload)
        assert signed.endswith("</ds:Signature>")
        assert verify_xml(signed, public_pem) is True

    def test_missing_digest_value_is_rejected(self):
        _, public_pem, _ = _material()
        broken = _XML + "<ds:Signature><ds:DigestValue>AAAA</ds:DigestValue></ds:Signature>"
        assert verify_xml(broken, public_pem) is False

    def test_invalid_base64_is_rejected(self):
        private_pem, public_pem, _ = _material()
        signed = sign_xml(_XML, private_pem)
        broken = re.sub(r"<ds:DigestValue>[^<]+</ds:DigestValue>", "<ds:DigestValue>A</ds:DigestValue>", signed)
        assert verify_xml(broken, public_pem) is False

    def test_verify_without_key_and_without_certificate_is_rejected(self):
        private_pem, _, _ = _material()
        assert verify_xml(sign_xml(_XML, private_pem)) is False

    def test_unparseable_embedded_certificate_is_rejected(self):
        private_pem, _, cert_pem = _material()
        signed = sign_xml(_XML, private_pem, certificate_pem=cert_pem)
        broken = re.sub(
            r"<ds:X509Certificate>[^<]+</ds:X509Certificate>",
            "<ds:X509Certificate>notacert</ds:X509Certificate>",
            signed,
        )
        assert verify_xml(broken) is False

    def test_unparseable_explicit_public_key_is_rejected(self):
        private_pem, _, _ = _material()
        assert verify_xml(sign_xml(_XML, private_pem), "not-a-key") is False

    def test_unsupported_key_types_are_rejected_on_both_paths(self):
        private_pem, public_pem, _ = _material()
        ed_key = ed25519.Ed25519PrivateKey.generate()
        ed_private = ed_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        ed_public = (
            ed_key.public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )
        with pytest.raises(ValueError, match="Unsupported ZATCA key type"):
            sign_xml(_XML, ed_private)
        assert verify_xml(sign_xml(_XML, private_pem), ed_public) is False

    def test_invalid_signature_is_rejected(self):
        private_pem, _, _ = _material()
        _, other_public, _ = _material()
        assert verify_xml(sign_xml(_XML, private_pem), other_public) is False
