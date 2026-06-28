"""Integration service — settings context, toggles, config lookup fallbacks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _service_row(enabled, config, status=None, tested_at=None):
    row = MagicMock()
    row.enabled = enabled
    row.get_config.return_value = config
    row.last_tested_at = tested_at
    row.last_test_status = status
    return row


class TestIntegrationsContext:
    """IntegrationService.get_integrations_context — four service blocks."""

    def test_returns_all_integration_blocks(self, mocker):
        mocker.patch(
            'models.integration_settings.IntegrationSettings.get_service_config',
            side_effect=lambda name: _service_row(
                enabled=name == 'whatsapp',
                config={'api_key': f'{name}_secret'},
                status='success' if name == 'email' else None,
            ),
        )
        from services.integration_service import IntegrationService

        ctx = IntegrationService.get_integrations_context()
        assert set(ctx.keys()) == {'whatsapp', 'email', 'redis', 'currency_api'}
        assert ctx['whatsapp']['enabled'] is True
        assert ctx['email']['status'] == 'success'
        assert ctx['redis']['status'] == 'not_configured'

    def test_disabled_service_reflects_toggle(self, mocker):
        mocker.patch(
            'models.integration_settings.IntegrationSettings.get_service_config',
            return_value=_service_row(False, {}, status='failed'),
        )
        from services.integration_service import IntegrationService

        ctx = IntegrationService.get_integrations_context()
        for block in ctx.values():
            assert block['enabled'] is False
            assert block['status'] == 'failed'


class TestIntegrationSettingsModel:
    """IntegrationSettings — init, config parse, credential storage round-trip."""

    def test_repr_shows_enabled_state(self):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name='whatsapp', enabled=True)
        assert 'whatsapp' in repr(row)

        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name='sms')
        row.config_data = None
        assert row.get_config() == {}

    def test_get_config_corrupted_json_fallback(self):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name='email', config_data='not-json{{{')
        assert row.get_config() == {}

    def test_set_and_get_config_roundtrip(self):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name='redis')
        creds = {'host': 'localhost', 'password': 'enc:abc123'}
        row.set_config(creds)
        assert row.get_config() == creds
        assert row.get_value('password') == 'enc:abc123'
        assert row.get_value('missing', 'default') == 'default'

    def test_set_value_updates_nested_config(self):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name='whatsapp')
        row.set_config({'token': 'old'})
        row.set_value('token', 'new_token')
        assert row.get_config()['token'] == 'new_token'

    def test_get_service_config_initializes_defaults(self, app, mocker):
        from models.integration_settings import IntegrationSettings

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            IntegrationSettings, 'query',
            new_callable=mocker.PropertyMock, return_value=mock_q,
        )
        mock_session = mocker.patch('models.integration_settings.db.session')

        with app.app_context():
            row = IntegrationSettings.get_service_config('currency_api')

        assert row.service_name == 'currency_api'
        assert row.enabled is False
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_to_dict_includes_enabled_toggle(self):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(
            service_name='email',
            enabled=True,
            config_data=json.dumps({'smtp_host': 'smtp.example.com'}),
            last_test_status='success',
            last_tested_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        d = row.to_dict()
        assert d['enabled'] is True
        assert d['config']['smtp_host'] == 'smtp.example.com'
        assert d['last_test_status'] == 'success'
