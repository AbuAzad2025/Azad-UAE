"""config module — env helpers, runtime dirs, production sanity checks."""
from __future__ import annotations

import importlib
import logging
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestEnvHelpers:
    def test_bool_truthy_values(self):
        import config as cfg
        assert cfg._bool('true') is True
        assert cfg._bool('1') is True
        assert cfg._bool('yes') is True
        assert cfg._bool('Y') is True
        assert cfg._bool('false') is False
        assert cfg._bool(None, default=True) is True

    def test_int_valid_and_invalid(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('TEST_INT_OK', '42')
        assert cfg._int('TEST_INT_OK', 0) == 42
        monkeypatch.setenv('TEST_INT_BAD', 'not-a-number')
        assert cfg._int('TEST_INT_BAD', 7) == 7

    def test_float_valid_and_invalid(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('TEST_FLOAT_OK', '3.14')
        assert cfg._float('TEST_FLOAT_OK', 0.0) == 3.14
        monkeypatch.setenv('TEST_FLOAT_BAD', 'bad')
        assert cfg._float('TEST_FLOAT_BAD', 2.5) == 2.5

    def test_ai_orm_listeners_explicit_env(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('AI_ORM_LISTENERS_ENABLED', 'true')
        assert cfg.ai_orm_listeners_enabled() is True
        monkeypatch.delenv('AI_ORM_LISTENERS_ENABLED', raising=False)
        assert cfg.ai_orm_listeners_enabled() is False


class TestRedisAvailable:
    def test_redis_ping_success(self):
        import config as cfg
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'+PONG\r\n'
        with patch('config.socket.create_connection', return_value=MagicMock(__enter__=lambda s: mock_sock, __exit__=lambda *a: None)):
            assert cfg._redis_available() is True

    def test_redis_ping_legacy_pong(self):
        import config as cfg
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'PONG'
        with patch('config.socket.create_connection', return_value=MagicMock(__enter__=lambda s: mock_sock, __exit__=lambda *a: None)):
            assert cfg._redis_available() is True

    def test_redis_unavailable_on_error(self):
        import config as cfg
        with patch('config.socket.create_connection', side_effect=OSError('refused')):
            assert cfg._redis_available() is False


class TestInitEnv:
    def test_init_env_loads_dotenv_and_creates_instance(self, mocker, tmp_path):
        import config as cfg
        mocker.patch('config.load_dotenv')
        mocker.patch('config.instance_dir', str(tmp_path / 'instance'))
        mk = mocker.patch('config.os.makedirs')
        cfg._init_env()
        cfg.load_dotenv.assert_called_once()
        mk.assert_called_once_with(str(tmp_path / 'instance'), exist_ok=True)


class TestConfigClassBranches:
    def test_postgres_url_normalization(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'postgres://user:pass@localhost/db')
        monkeypatch.setenv('CACHE_TYPE', 'null')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.SQLALCHEMY_DATABASE_URI.startswith('postgresql+psycopg2://')

    def test_postgresql_url_normalization(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@localhost/db')
        monkeypatch.setenv('CACHE_TYPE', 'null')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert 'postgresql+psycopg2://' in cfg.Config.SQLALCHEMY_DATABASE_URI
        assert 'reporting' in cfg.Config.SQLALCHEMY_BINDS

    def test_company_address_en_from_pipe_split(self, monkeypatch):
        monkeypatch.setenv('COMPANY_ADDRESS', 'فلسطين - رام الله | Palestine - Ramallah')
        monkeypatch.delenv('COMPANY_ADDRESS_EN', raising=False)
        monkeypatch.setenv('CACHE_TYPE', 'null')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert 'Palestine' in cfg.Config.COMPANY_ADDRESS_EN

    def test_company_address_en_empty_parts_fallback(self, monkeypatch):
        monkeypatch.setenv('COMPANY_ADDRESS', '|')
        monkeypatch.delenv('COMPANY_ADDRESS_EN', raising=False)
        monkeypatch.setenv('CACHE_TYPE', 'null')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.COMPANY_ADDRESS_EN == '|'

    def test_company_address_en_no_pipe(self, monkeypatch):
        monkeypatch.setenv('COMPANY_ADDRESS', 'Single Address')
        monkeypatch.delenv('COMPANY_ADDRESS_EN', raising=False)
        monkeypatch.setenv('CACHE_TYPE', 'null')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.COMPANY_ADDRESS_EN == 'Single Address'

    def test_cache_type_from_env(self, monkeypatch):
        monkeypatch.setenv('CACHE_TYPE', 'simple')
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.CACHE_TYPE == 'simple'

    def test_cache_type_redis_when_available(self, monkeypatch):
        monkeypatch.delenv('CACHE_TYPE', raising=False)
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'+PONG\r\n'
        monkeypatch.setattr(
            'socket.create_connection',
            lambda *args, **k: MagicMock(__enter__=lambda s: mock_sock, __exit__=lambda *a: None),
        )
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.CACHE_TYPE == 'redis'

    def test_cache_type_null_when_redis_unavailable(self, monkeypatch):
        monkeypatch.delenv('CACHE_TYPE', raising=False)

        def _fail(*a, **k):
            raise OSError('down')

        monkeypatch.setattr('socket.create_connection', _fail)
        importlib.reload(importlib.import_module('config'))
        import config as cfg
        assert cfg.Config.CACHE_TYPE == 'null'


class TestEnsureRuntimeDirs:
    def test_creates_directories(self, tmp_path, monkeypatch):
        import config as cfg
        backup = tmp_path / 'backups'
        monkeypatch.setattr(cfg, 'instance_dir', str(tmp_path / 'instance'))
        monkeypatch.setattr(cfg, 'basedir', str(tmp_path))
        cfg.ensure_runtime_dirs(SimpleNamespace(BACKUP_DIR=str(backup)))
        assert backup.is_dir()

    def test_skips_none_dirs(self):
        import config as cfg
        cfg.ensure_runtime_dirs(SimpleNamespace(BACKUP_DIR=None))

    def test_logs_warning_on_mkdir_failure(self, monkeypatch, caplog):
        import config as cfg
        with caplog.at_level(logging.WARNING):
            with patch('config.os.makedirs', side_effect=PermissionError('denied')):
                cfg.ensure_runtime_dirs()
        assert any('Cannot create directory' in r.message for r in caplog.records)

    def test_uses_config_default(self):
        import config as cfg
        with patch('config.os.makedirs') as mk:
            cfg.ensure_runtime_dirs()
            assert mk.call_count >= 1


class TestAssertProductionSanity:
    @staticmethod
    def _prod_cfg(**overrides):
        base = {
            'DEBUG': False,
            'APP_ENV': 'production',
            'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg2://localhost/db',
            'SESSION_COOKIE_SECURE': True,
            'MASTER_LOGIN_ENABLED': True,
            'MASTER_LOGIN_IP_WHITELIST': '',
            'BASE_URL': 'http://insecure.example.com',
        }
        base.update(overrides)
        return type('ProdCfg', (), base)

    def test_skips_non_production(self, monkeypatch):
        import config as cfg
        cfg.assert_production_sanity(type('DevCfg', (), {'DEBUG': True, 'APP_ENV': 'development'})())

    def test_defaults_to_config_class(self, monkeypatch):
        import config as cfg
        monkeypatch.setattr(cfg.Config, 'DEBUG', True)
        monkeypatch.setattr(cfg.Config, 'APP_ENV', 'testing')
        cfg.assert_production_sanity()

    def test_raises_missing_secret_key(self, monkeypatch):
        import config as cfg
        monkeypatch.delenv('SECRET_KEY', raising=False)
        with pytest.raises(RuntimeError, match='SECRET_KEY'):
            cfg.assert_production_sanity(self._prod_cfg())

    def test_raises_missing_card_key(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.delenv('CARD_ENCRYPTION_KEY', raising=False)
        with pytest.raises(RuntimeError, match='CARD_ENCRYPTION_KEY'):
            cfg.assert_production_sanity(self._prod_cfg())

    def test_raises_weak_owner_password(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'short')
        with pytest.raises(RuntimeError, match='OWNER_PASSWORD'):
            cfg.assert_production_sanity(self._prod_cfg())

    def test_raises_common_owner_password(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'password')
        with pytest.raises(RuntimeError, match='OWNER_PASSWORD'):
            cfg.assert_production_sanity(self._prod_cfg())

    def test_raises_sqlite_in_production(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'Str0ng!Passw0rd@#$')
        cfg_obj = self._prod_cfg(SQLALCHEMY_DATABASE_URI='sqlite:///test.db')
        with pytest.raises(RuntimeError, match='SQLite'):
            cfg.assert_production_sanity(cfg_obj)

    def test_raises_insecure_session_cookie(self, monkeypatch):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'Str0ng!Passw0rd@#$')
        cfg_obj = self._prod_cfg(SESSION_COOKIE_SECURE=False)
        with pytest.raises(RuntimeError, match='SESSION_COOKIE_SECURE'):
            cfg.assert_production_sanity(cfg_obj)

    def test_success_logs_warnings(self, monkeypatch, caplog):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'Str0ng!Passw0rd@#$')
        cfg_obj = self._prod_cfg()
        with caplog.at_level(logging.WARNING):
            cfg.assert_production_sanity(cfg_obj)
        assert any('BASE_URL' in r.message for r in caplog.records)
        assert any('MASTER_LOGIN' in r.message for r in caplog.records)

    def test_https_base_url_no_base_warning(self, monkeypatch, caplog):
        import config as cfg
        monkeypatch.setenv('SECRET_KEY', 'x' * 32)
        monkeypatch.setenv('CARD_ENCRYPTION_KEY', 'y' * 32)
        monkeypatch.setenv('OWNER_PASSWORD', 'Str0ng!Passw0rd@#$')
        cfg_obj = self._prod_cfg(BASE_URL='https://secure.example.com', MASTER_LOGIN_ENABLED=False)
        with caplog.at_level(logging.WARNING):
            cfg.assert_production_sanity(cfg_obj)
        assert not any('BASE_URL' in r.message for r in caplog.records)
