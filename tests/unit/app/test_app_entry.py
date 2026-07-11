from __future__ import annotations

import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP_PY = ROOT / 'app.py'


class TestAppEntry:
    def test_root_app_py_exposes_flask_app(self):
        spec_name = 'azad_app_entry'
        if spec_name in sys.modules:
            del sys.modules[spec_name]
        import importlib.util
        spec = importlib.util.spec_from_file_location(spec_name, APP_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.app is not None
        assert hasattr(mod.app, 'test_client')

    def test_create_app_factory_without_persistent_port(self):
        from app.factory import create_app
        from tests.conftest import TestConfig
        application = create_app(config_class=TestConfig)
        with application.test_client() as client:
            assert client is not None

    def test_main_masks_db_uri_and_runs_app(self, monkeypatch):
        fake_app = MagicMock()
        fake_app.config = {'DEBUG': False, 'SQLALCHEMY_DATABASE_URI': 'postgresql://user:secret@localhost/db'}
        fake_app.logger = MagicMock()
        fake_app.run = MagicMock()
        with patch.dict('os.environ', {'PORT': '59999', 'HOST': '127.0.0.1'}), patch(
            'services.backup_service.BackupService.initialize'
        ), patch('services.auto_approval_service.schedule_auto_approval'), patch(
            'app.factory.create_app', return_value=fake_app
        ):
            runpy.run_path(str(APP_PY), run_name='__main__')
        fake_app.run.assert_called_once()
        assert fake_app.run.call_args.kwargs['port'] == 59999

    def test_main_handles_startup_failure(self):
        with patch('app.factory.create_app', side_effect=RuntimeError('boot fail')):
            with pytest.raises(RuntimeError):
                runpy.run_path(str(APP_PY), run_name='__main__')

    def test_auto_approval_failure_is_non_fatal(self):
        fake_app = MagicMock()
        fake_app.config = {'DEBUG': False, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///x'}
        fake_app.logger = MagicMock()
        with patch.dict('os.environ', {'PORT': '5002', 'HOST': '127.0.0.1'}), patch(
            'services.backup_service.BackupService.initialize'
        ), patch('services.auto_approval_service.schedule_auto_approval', side_effect=RuntimeError('sched')), patch(
            'app.factory.create_app', return_value=fake_app
        ):
            runpy.run_path(str(APP_PY), run_name='__main__')
        fake_app.logger.warning.assert_called()
