"""SystemSettings model — get_current, custom JSON, to_dict."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class TestSystemSettingsModel:
    def test_get_current_creates_when_missing(self, app, mocker):
        from models.system_settings import SystemSettings

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(SystemSettings, 'query', mock_q)
        mock_session = mocker.patch('models.system_settings.db.session')
        with app.app_context():
            settings = SystemSettings.get_current()
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        assert isinstance(settings, SystemSettings)

    def test_get_current_returns_existing(self, app, mocker):
        from models.system_settings import SystemSettings

        existing = SystemSettings()
        existing.system_name = 'Azad'
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(SystemSettings, 'query', mock_q)
        with app.app_context():
            assert SystemSettings.get_current() is existing

    def test_get_custom_setting_valid_json(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.custom_settings = json.dumps({'theme': 'dark'})
        assert s.get_custom_setting('theme') == 'dark'
        assert s.get_custom_setting('missing', 'x') == 'x'

    def test_get_custom_setting_invalid_json(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.custom_settings = '{bad'
        assert s.get_custom_setting('k', 'default') == 'default'

    def test_set_custom_setting_merges(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.custom_settings = json.dumps({'a': 1})
        s.set_custom_setting('b', 2)
        data = json.loads(s.custom_settings)
        assert data == {'a': 1, 'b': 2}

    def test_set_custom_setting_invalid_existing_json(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.custom_settings = 'not-json'
        s.set_custom_setting('k', 'v')
        assert json.loads(s.custom_settings) == {'k': 'v'}

    def test_to_dict(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.system_name = 'ERP'
        s.system_version = '1.0'
        s.theme = 'light'
        s.default_language = 'ar'
        s.default_currency = 'AED'
        s.timezone = 'Asia/Dubai'
        s.is_active = True
        d = s.to_dict()
        assert d['system_name'] == 'ERP'
        assert d['is_active'] is True

    def test_get_custom_setting_no_json_blob(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.custom_settings = None
        assert s.get_custom_setting('k', 'default') == 'default'

    def test_repr(self):
        from models.system_settings import SystemSettings

        s = SystemSettings()
        s.system_name = 'Test'
        assert 'Test' in repr(s)
