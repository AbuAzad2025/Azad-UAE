from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from app.integrity import _is_migration_command, run_system_integrity_check


class TestIntegrity:
    def test_is_migration_command_db(self):
        with patch.object(sys, 'argv', ['flask', 'db', 'upgrade']):
            assert _is_migration_command() is True

    def test_is_migration_command_normal(self):
        with patch.object(sys, 'argv', ['flask', 'run']):
            assert _is_migration_command() is False

    def test_run_skipped_on_env(self):
        app = MagicMock()
        with patch.dict('os.environ', {'SKIP_SYSTEM_INTEGRITY': '1'}):
            run_system_integrity_check(app)
        app.logger.info.assert_not_called()

    def test_run_skipped_on_migration(self):
        app = MagicMock()
        with patch('app.integrity._is_migration_command', return_value=True):
            run_system_integrity_check(app)
        app.logger.info.assert_not_called()

    def test_run_success(self):
        app = MagicMock()
        with patch.dict('os.environ', {}, clear=True), \
             patch('app.integrity._is_migration_command', return_value=False), \
             patch('utils.system_init.ensure_system_integrity') as ensure:
            run_system_integrity_check(app)
            ensure.assert_called_once_with(app)
            app.logger.info.assert_called()

    def test_run_logs_error_on_failure(self):
        app = MagicMock()
        with patch.dict('os.environ', {}, clear=True), \
             patch('app.integrity._is_migration_command', return_value=False), \
             patch('utils.system_init.ensure_system_integrity', side_effect=RuntimeError('fail')):
            run_system_integrity_check(app)
            app.logger.error.assert_called()
