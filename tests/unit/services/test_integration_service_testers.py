"""IntegrationService — SMTP test send and currency-API probe paths.

Covers ``_build_currency_test_url`` URL construction rules and every
outcome branch of ``test_email`` / ``test_currency_api``, asserting both the
returned ``(ok, message)`` tuple and the recorded last-test state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


def _integration_row(config):
    row = MagicMock()
    row.service_name = "row"
    row.enabled = True
    row.get_config.return_value = config
    return row


@pytest.fixture
def settings_spy(mocker):
    """Patch IntegrationSettings.get_service_config; returns (factory, calls)."""
    rows = {}

    def _register(service_name, config):
        row = _integration_row(config)
        rows[service_name] = row
        return row

    mocker.patch(
        "models.integration_settings.IntegrationSettings.get_service_config",
        side_effect=lambda name: rows.get(name) or _register(name, {}),
    )
    return rows


def _assert_recorded(row, ok, message_fragment=None):
    assert isinstance(row.last_tested_at, datetime)
    assert row.last_tested_at.tzinfo is UTC or row.last_tested_at.tzinfo is not None
    assert row.last_test_status == ("success" if ok else "failed")
    if message_fragment is not None:
        assert message_fragment in row.last_test_message


class TestBuildCurrencyTestUrl:
    def test_stored_api_url_wins_with_placeholder_substitution(self):
        from services.integration_service import IntegrationService

        url = IntegrationService._build_currency_test_url(
            {"api_url": "https://api.example.test/rate?key={api_key}&base={base}", "api_key": "K-123", "base_currency": "aed"}
        )
        assert url == "https://api.example.test/rate?key=K-123&base=AED"

    def test_no_url_and_no_key_returns_none(self):
        from services.integration_service import IntegrationService

        assert IntegrationService._build_currency_test_url({}) is None
        assert IntegrationService._build_currency_test_url({"api_key": ""}) is None

    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            (
                "exchangerate",
                "https://v6.exchangerate-api.com/v6/kk/latest/USD",
            ),
            ("fixer", "https://data.fixer.io/api/latest?access_key=kk&base=USD"),
            ("currencyapi", "https://api.currencyapi.com/v3/latest?apikey=kk&base_currency=USD"),
        ],
    )
    def test_known_provider_templates(self, provider, expected):
        from services.integration_service import IntegrationService

        url = IntegrationService._build_currency_test_url({"api_key": "kk", "api_provider": provider})
        assert url == expected

    def test_unknown_provider_returns_none(self):
        from services.integration_service import IntegrationService

        url = IntegrationService._build_currency_test_url({"api_key": "kk", "api_provider": "mystery"})
        assert url is None


class TestCurrencyApiTester:
    def _service(self):
        from services.integration_service import IntegrationService

        return IntegrationService

    def test_unconfigured_service_fails_and_records(self, app, settings_spy):
        ok, message = self._service().test_currency_api()
        assert ok is False
        assert "غير مهيأ" in message
        _assert_recorded(settings_spy["currency_api"], False)

    def test_connection_error_records_failure(self, app, settings_spy, mocker):
        mocker.patch(
            "services.integration_service.requests.get",
            side_effect=ConnectionError("dns fail"),
        )
        settings_spy["currency_api"] = _integration_row({"api_key": "kk"})
        ok, message = self._service().test_currency_api()
        assert ok is False
        assert "dns fail" in message
        _assert_recorded(settings_spy["currency_api"], False)

    def test_non_200_response_fails(self, app, settings_spy, mocker):
        response = MagicMock(status_code=503)
        mocker.patch("services.integration_service.requests.get", return_value=response)
        settings_spy["currency_api"] = _integration_row({"api_key": "kk"})
        ok, message = self._service().test_currency_api()
        assert ok is False
        assert "503" in message
        _assert_recorded(settings_spy["currency_api"], False)

    def test_non_json_body_fails(self, app, settings_spy, mocker):
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("not json")
        mocker.patch("services.integration_service.requests.get", return_value=response)
        settings_spy["currency_api"] = _integration_row({"api_key": "kk"})
        ok, message = self._service().test_currency_api()
        assert ok is False
        assert "JSON" in message
        _assert_recorded(settings_spy["currency_api"], False)

    def test_valid_json_response_succeeds(self, app, settings_spy, mocker):
        response = MagicMock(status_code=200)
        response.json.return_value = {"rates": {"AED": 3.67}}
        mocker.patch("services.integration_service.requests.get", return_value=response)
        settings_spy["currency_api"] = _integration_row({"api_key": "kk"})
        ok, message = self._service().test_currency_api()
        assert ok is True
        _assert_recorded(settings_spy["currency_api"], True)


class TestEmailTester:
    def _service(self):
        from services.integration_service import IntegrationService

        return IntegrationService

    def test_missing_sender_config_fails_before_send(self, app, settings_spy):
        settings_spy["email"] = _integration_row({"smtp_host": "smtp.test"})
        ok, message = self._service().test_email()
        assert ok is False
        assert "غير مهيأ" in message
        _assert_recorded(settings_spy["email"], False)

    def test_smtp_username_used_as_sender_when_from_email_absent(self, app, settings_spy, mocker):
        send = mocker.patch("services.integration_service.mail.send")
        settings_spy["email"] = _integration_row(
            {"smtp_user": "erp@test.local", "sender_name": "Azadexa"}
        )
        ok, message = self._service().test_email()
        assert ok is True
        sent = send.call_args.args[0]
        assert sent.recipients == ["erp@test.local"]
        assert sent.sender == ("Azadexa", "erp@test.local")
        _assert_recorded(settings_spy["email"], True, "erp@test.local")

    def test_send_failure_records_exception(self, app, settings_spy, mocker):
        mocker.patch(
            "services.integration_service.mail.send",
            side_effect=RuntimeError("SMTP refused"),
        )
        settings_spy["email"] = _integration_row({"from_email": "ops@test.local"})
        ok, message = self._service().test_email()
        assert ok is False
        assert "SMTP refused" in message
        _assert_recorded(settings_spy["email"], False)

    def test_plain_string_sender_when_no_name(self, app, settings_spy, mocker):
        send = mocker.patch("services.integration_service.mail.send")
        settings_spy["email"] = _integration_row({"from_email": "noreply@test.local"})
        ok, _ = self._service().test_email()
        assert ok is True
        sent = send.call_args.args[0]
        assert sent.sender == "noreply@test.local"
