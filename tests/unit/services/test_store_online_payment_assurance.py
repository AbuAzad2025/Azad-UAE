"""Store online payment — gateway create, order-id parsing, rollback on failure."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestConfiguration:
    """is_configured / _api_key — vault and platform key matrix."""

    def test_not_configured_without_vault_key(self, app, mocker):
        mocker.patch(
            "services.store_online_payment_service.PaymentVault.get_tenant_vault",
            return_value=None,
        )
        mocker.patch(
            "services.store_online_payment_service.PaymentVault.get_platform_vault",
            return_value=None,
        )

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            assert StoreOnlinePaymentService.is_configured(1) is False

    def test_configured_via_tenant_vault(self, app, mocker):
        vault = MagicMock(nowpayments_api_key="sk-test")
        mocker.patch(
            "services.store_online_payment_service.PaymentVault.get_tenant_vault",
            return_value=vault,
        )

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            assert StoreOnlinePaymentService.is_configured(1) is True

    def test_api_key_raises_when_missing(self, app, mocker):
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService._vault_for_tenant",
            return_value=None,
        )

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            app.config["NOWPAYMENTS_API_KEY"] = ""
            with pytest.raises(ValueError, match="غير مهيأة"):
                StoreOnlinePaymentService._api_key(1)


class TestOrderIdParsing:
    """parse_store_order_id — webhook order reference validation."""

    @pytest.mark.parametrize(
        "order_id,expected",
        [
            ("STORE_42_7", (42, 7)),
            ("STORE_1_99", (1, 99)),
            ("INVALID_1_2", None),
            ("", None),
            ("STORE_bad", None),
        ],
    )
    def test_parse_matrix(self, order_id, expected):
        from services.store_online_payment_service import StoreOnlinePaymentService

        assert StoreOnlinePaymentService.parse_store_order_id(order_id) == expected


class TestCreatePayment:
    """create_payment_for_sale — API call, status mapping, DB rollback."""

    def test_rejects_below_minimum_aed(self, app, mocker):
        sale = MagicMock(amount_aed=Decimal("0.5"), total_amount=0.5)
        store = MagicMock(tenant_id=1, title="S")
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService._api_key",
            return_value="key",
        )

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            with pytest.raises(ValueError, match="الحد الأدنى"):
                StoreOnlinePaymentService.create_payment_for_sale(sale, store)

    def test_gateway_failure_raises(self, app, mocker):
        sale = MagicMock(
            id=10,
            sale_number="S-10",
            amount_aed=Decimal("100"),
            total_amount=100,
            currency="AED",
            checkout_payment_method=None,
        )
        store = MagicMock(tenant_id=2, title="Shop")
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService._api_key",
            return_value="key",
        )
        mocker.patch(
            "services.store_online_payment_service.get_nowpayments_ipn_url",
            return_value="https://ipn",
        )
        resp = MagicMock(status_code=400, text="bad request")
        mocker.patch("services.store_online_payment_service.requests.post", return_value=resp)

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            with pytest.raises(ValueError, match="فشل إنشاء الدفع"):
                StoreOnlinePaymentService.create_payment_for_sale(sale, store)

    def test_success_commits_gateway_ref(self, app, mocker):
        sale = MagicMock(
            id=5,
            sale_number="S-5",
            amount_aed=Decimal("50"),
            total_amount=50,
            currency="aed",
            checkout_payment_method=None,
        )
        store = MagicMock(tenant_id=3, title="Store")
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService._api_key",
            return_value="key",
        )
        mocker.patch(
            "services.store_online_payment_service.get_nowpayments_ipn_url",
            return_value="https://ipn",
        )
        resp = MagicMock(status_code=201)
        resp.json.return_value = {"payment_id": "pid-1", "invoice_url": "https://pay"}
        mocker.patch("services.store_online_payment_service.requests.post", return_value=resp)
        mock_session = mocker.patch("services.store_online_payment_service.db.session")

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            result = StoreOnlinePaymentService.create_payment_for_sale(sale, store, customer_email="a@b.com")

        assert result["payment_url"] == "https://pay"
        assert sale.checkout_gateway_ref == "pid-1"
        mock_session.flush.assert_called_once()

    def test_commit_failure_rolls_back(self, app, mocker):
        sale = MagicMock(
            id=6,
            sale_number="S-6",
            amount_aed=Decimal("20"),
            total_amount=20,
            currency="aed",
            checkout_payment_method="cod",
        )
        store = MagicMock(tenant_id=1, title="X")
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService._api_key",
            return_value="key",
        )
        mocker.patch(
            "services.store_online_payment_service.get_nowpayments_ipn_url",
            return_value="https://ipn",
        )
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"payment_id": "p2", "payment_url": "https://u"}
        mocker.patch("services.store_online_payment_service.requests.post", return_value=resp)
        mock_session = mocker.patch("services.store_online_payment_service.db.session")
        mock_session.flush.side_effect = RuntimeError("db")

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            with pytest.raises(RuntimeError):
                StoreOnlinePaymentService.create_payment_for_sale(sale, store)
