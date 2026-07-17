from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils import nowpayments_ipn as nip


class TestGetNowpaymentsIpnUrl:
    def test_delegates_to_provider(self):
        provider = MagicMock()
        provider.build_webhook_url.return_value = (
            "https://example.com/webhook/nowpayments"
        )
        with patch(
            "services.payments.nowpayments_provider.NowPaymentsProvider",
            return_value=provider,
        ):
            assert (
                nip.get_nowpayments_ipn_url()
                == "https://example.com/webhook/nowpayments"
            )
        provider.build_webhook_url.assert_called_once()


class TestResolveNowpaymentsIpnSecret:
    def test_vault_argument_takes_priority(self):
        vault = MagicMock(nowpayments_ipn_secret="  vault-secret  ")
        assert nip.resolve_nowpayments_ipn_secret(vault=vault) == "vault-secret"

    def test_vault_empty_falls_through_to_db(self):
        vault = MagicMock(nowpayments_ipn_secret="")
        row = MagicMock(nowpayments_ipn_secret="db-secret")
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault", return_value=row
        ):
            assert nip.resolve_nowpayments_ipn_secret(vault=vault) == "db-secret"

    def test_db_lookup_when_no_vault_arg(self):
        row = MagicMock(nowpayments_ipn_secret="platform-secret")
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault", return_value=row
        ):
            assert nip.resolve_nowpayments_ipn_secret() == "platform-secret"

    def test_db_exception_falls_back_to_provider(self):
        provider = MagicMock()
        provider.ipn_secret = " env-fallback "
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                side_effect=RuntimeError("db down"),
            ),
            patch(
                "services.payments.nowpayments_provider.NowPaymentsProvider",
                return_value=provider,
            ),
        ):
            assert nip.resolve_nowpayments_ipn_secret() == "env-fallback"

    def test_empty_db_and_provider_returns_empty(self):
        provider = MagicMock(ipn_secret=None)
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                return_value=None,
            ),
            patch(
                "services.payments.nowpayments_provider.NowPaymentsProvider",
                return_value=provider,
            ),
        ):
            assert nip.resolve_nowpayments_ipn_secret() == ""

    def test_whitespace_only_vault_secret_skipped(self):
        vault = MagicMock(nowpayments_ipn_secret="   ")
        provider = MagicMock(ipn_secret="provider-secret")
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                return_value=None,
            ),
            patch(
                "services.payments.nowpayments_provider.NowPaymentsProvider",
                return_value=provider,
            ),
        ):
            assert nip.resolve_nowpayments_ipn_secret(vault=vault) == "provider-secret"
