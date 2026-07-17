"""Unit tests for NOWPaymentsService."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import requests

from extensions import db
from models import Donation
from services.nowpayments_service import NOWPaymentsService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def svc():
    service = NOWPaymentsService()
    service.api_key = "test-api-key"
    service.api_url = "https://api.nowpayments.test/v1"
    service.ipn_secret = "ipn-secret"
    return service


def _ok_post(payload=None, payment_id="np-100"):
    def fake_post(url, json_data=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 201
        base = {
            "payment_id": payment_id,
            "pay_address": "bc1qtest",
            "pay_amount": 0.001,
            "payment_url": f"https://pay.example/{payment_id}",
            "order_id": json_data.get("order_id") if json_data else None,
            "expires_at": "2026-12-31T00:00:00Z",
        }
        if payload:
            base.update(payload)
        resp.json.return_value = base
        return resp

    return fake_post


def _ipn_sig(secret: str, data: dict) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        json.dumps(data, sort_keys=True).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class TestCreatePayment:
    def test_rejects_amount_below_minimum(self, svc):
        result = svc.create_payment(amount=0.5)
        assert result["success"] is False
        assert "الحد الأدنى" in result["error"]

    def test_creates_donation_and_returns_payment(self, svc, db_session, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.post", side_effect=_ok_post()
        )
        mocker.patch(
            "services.nowpayments_service.get_nowpayments_ipn_url",
            return_value="https://example.com/payment-vault/webhook/nowpayments",
        )

        result = svc.create_payment(
            amount=25,
            order_id="DON-1",
            customer_email="donor@example.com",
            donor_name="Ali",
            donor_email="donor@example.com",
            donor_message="thanks",
        )

        assert result["success"] is True
        assert result["payment_id"] == "np-100"
        donation = Donation.query.filter_by(gateway_transaction_id="np-100").first()
        assert donation is not None
        assert donation.amount_usd == Decimal("25")
        assert donation.donor_name == "Ali"
        assert donation.customer_email == "donor@example.com"

    def test_purchase_transaction_maps_customer_fields(self, svc, db_session, mocker):
        payment_id = f"np-purchase-{uuid.uuid4().hex[:12]}"
        mocker.patch(
            "services.nowpayments_service.requests.post",
            side_effect=_ok_post(payment_id=payment_id),
        )
        mocker.patch(
            "services.nowpayments_service.get_nowpayments_ipn_url",
            return_value="https://ipn",
        )

        result = svc.create_payment(
            amount=99,
            transaction_type="purchase",
            package="pro",
            customer_name="Buyer",
            customer_email="buyer@example.com",
            customer_phone="+971500000000",
        )

        assert result["success"] is True
        donation = Donation.query.filter_by(gateway_transaction_id=payment_id).one()
        assert donation.transaction_type == "purchase"
        assert donation.package == "pro"
        assert donation.customer_name == "Buyer"
        assert donation.customer_phone == "+971500000000"

    def test_omits_optional_order_and_email(self, svc, mocker):
        captured = {}

        def fake_post(url, json_data=None, headers=None, timeout=None):
            captured.update(json_data or {})
            return _ok_post()(
                url, json_data=json_data, headers=headers, timeout=timeout
            )

        mocker.patch(
            "services.nowpayments_service.requests.post", side_effect=fake_post
        )
        mocker.patch(
            "services.nowpayments_service.get_nowpayments_ipn_url",
            return_value="https://ipn",
        )
        mocker.patch.object(db.session, "add")
        mocker.patch.object(db.session, "commit")

        result = svc.create_payment(amount=10, description="Custom desc")

        assert result["success"] is True
        assert "order_id" not in captured
        assert "customer_email" not in captured
        assert captured["order_description"] == "Custom desc"

    def test_api_non_201_returns_error(self, svc, mocker):
        resp = MagicMock(status_code=400, text="bad request")
        mocker.patch("services.nowpayments_service.requests.post", return_value=resp)

        result = svc.create_payment(amount=10)
        assert result["success"] is False
        assert "NOWPayments" in result["error"]

    def test_request_exception_returns_connection_error(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.post",
            side_effect=requests.exceptions.Timeout("timeout"),
        )
        result = svc.create_payment(amount=10)
        assert result["success"] is False
        assert "الاتصال" in result["error"]

    def test_unexpected_exception_returns_generic_error(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.post",
            side_effect=RuntimeError("boom"),
        )
        result = svc.create_payment(amount=10)
        assert result["success"] is False

    def test_db_commit_failure_returns_error(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.post", side_effect=_ok_post()
        )
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("db fail"))

        result = svc.create_payment(amount=10)
        assert result["success"] is False


class TestGetPaymentStatus:
    def test_success(self, svc, mocker):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"payment_status": "finished"}
        mocker.patch("services.nowpayments_service.requests.get", return_value=resp)

        result = svc.get_payment_status("np-1")
        assert result["success"] is True
        assert result["data"]["payment_status"] == "finished"

    def test_non_200(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            return_value=MagicMock(status_code=404),
        )
        result = svc.get_payment_status("missing")
        assert result["success"] is False

    def test_exception(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            side_effect=RuntimeError("net"),
        )
        result = svc.get_payment_status("np-1")
        assert result["success"] is False


class TestGetAvailableCurrencies:
    def test_success(self, svc, mocker):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"currencies": ["btc", "eth"]}
        mocker.patch("services.nowpayments_service.requests.get", return_value=resp)

        result = svc.get_available_currencies()
        assert result["success"] is True
        assert "btc" in result["currencies"]["currencies"]

    def test_non_200(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            return_value=MagicMock(status_code=500),
        )
        assert svc.get_available_currencies()["success"] is False

    def test_exception(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            side_effect=RuntimeError("down"),
        )
        assert svc.get_available_currencies()["success"] is False


class TestGetEstimatedAmount:
    def test_success(self, svc, mocker):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"estimated_amount": 0.01}
        mocker.patch("services.nowpayments_service.requests.get", return_value=resp)

        result = svc.get_estimated_amount(100, from_currency="usd", to_currency="btc")
        assert result["success"] is True
        assert result["data"]["estimated_amount"] == 0.01

    def test_non_200(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            return_value=MagicMock(status_code=422),
        )
        assert svc.get_estimated_amount(50)["success"] is False

    def test_exception(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.requests.get",
            side_effect=RuntimeError("err"),
        )
        assert svc.get_estimated_amount(50)["success"] is False


class TestVerifyIpn:
    def test_valid_signature(self, svc):
        data = {"payment_id": "np-1", "payment_status": "finished"}
        sig = _ipn_sig(svc.ipn_secret, data)
        assert svc.verify_ipn(data, sig) is True

    def test_invalid_signature(self, svc):
        assert svc.verify_ipn({"payment_id": "x"}, "bad-sig") is False

    def test_exception_returns_false(self, svc, mocker):
        mocker.patch(
            "services.nowpayments_service.json.dumps", side_effect=TypeError("bad")
        )
        assert svc.verify_ipn({"a": 1}, "sig") is False


class TestProcessPaymentCallback:
    @staticmethod
    def _donation(db_session, payment_id=None):
        if payment_id is None:
            payment_id = f"np-cb-{uuid.uuid4().hex[:12]}"
        row = Donation(
            amount_usd=Decimal("20"),
            payment_method="crypto",
            crypto_type="btc",
            transaction_hash=payment_id,
            gateway_transaction_id=payment_id,
            status="pending",
            gateway_name="nowpayments",
        )
        db_session.add(row)
        db_session.commit()
        return row

    def test_missing_payment_id(self, svc):
        assert svc.process_payment_callback({"payment_status": "finished"}) is False

    def test_unknown_donation(self, svc):
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": "missing",
                    "payment_status": "finished",
                }
            )
            is False
        )

    def test_finished_marks_completed(self, svc, db_session):
        payment_id = f"np-finish-{uuid.uuid4().hex[:12]}"
        d = self._donation(db_session, payment_id=payment_id)
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": payment_id,
                    "payment_status": "finished",
                }
            )
            is True
        )
        db_session.refresh(d)
        assert d.status == "completed"
        assert d.completed_at is not None

    def test_failed_and_refunded_statuses(self, svc, db_session):
        fail_id = f"np-fail-{uuid.uuid4().hex[:12]}"
        d_fail = self._donation(db_session, payment_id=fail_id)
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": fail_id,
                    "payment_status": "failed",
                }
            )
            is True
        )
        db_session.refresh(d_fail)
        assert d_fail.status == "failed"

        ref_id = f"np-ref-{uuid.uuid4().hex[:12]}"
        d_ref = self._donation(db_session, payment_id=ref_id)
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": ref_id,
                    "payment_status": "refunded",
                }
            )
            is True
        )
        db_session.refresh(d_ref)
        assert d_ref.status == "refunded"

    def test_finds_by_transaction_hash_only(self, svc, db_session):
        row = Donation(
            amount_usd=Decimal("15"),
            payment_method="crypto",
            transaction_hash="hash-only",
            status="pending",
            gateway_name="nowpayments",
        )
        db_session.add(row)
        db_session.commit()

        assert (
            svc.process_payment_callback(
                {
                    "payment_id": "hash-only",
                    "payment_status": "finished",
                }
            )
            is True
        )

    def test_other_status_leaves_donation_pending(self, svc, db_session):
        d = self._donation(db_session, payment_id="np-wait")
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": "np-wait",
                    "payment_status": "waiting",
                }
            )
            is True
        )
        db_session.refresh(d)
        assert d.status == "pending"

    def test_commit_failure_returns_false(self, svc, db_session, mocker):
        self._donation(db_session, payment_id="np-db-fail")
        mocker.patch.object(
            db.session, "commit", side_effect=RuntimeError("commit fail")
        )

        assert (
            svc.process_payment_callback(
                {
                    "payment_id": "np-db-fail",
                    "payment_status": "finished",
                }
            )
            is False
        )

    def test_unexpected_exception_returns_false(self, svc, mocker):
        mock_q = mocker.MagicMock()
        mock_q.filter.side_effect = RuntimeError("q")
        mocker.patch("services.nowpayments_service.Donation.query", mock_q)
        assert (
            svc.process_payment_callback(
                {
                    "payment_id": "x",
                    "payment_status": "finished",
                }
            )
            is False
        )
