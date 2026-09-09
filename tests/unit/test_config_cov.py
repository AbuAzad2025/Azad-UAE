"""Residual-line/arc coverage for config.py.

Targets (branch coverage):
- line 162: ``CORS_ORIGINS`` containing ``'*'`` raises ``ValueError``.
- lines 171-176: ``RATELIMIT_STORAGE_URI`` resolution — explicit env value,
  ``REDIS_URL`` fallback when Redis is reachable, ``memory://`` fallback.
- arc 110->115: non-postgresql ``DATABASE_URL`` skips the postgres pool block.
- arc 116->119: non-postgresql ``DATABASE_URL`` skips the reporting bind.
- arc 258->267: explicit ``COMPANY_ADDRESS_EN`` env skips address derivation.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


def _reload_config():
    return importlib.reload(importlib.import_module("config"))


@pytest.fixture(autouse=True)
def _restore_config_module(monkeypatch):
    yield
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    _reload_config()


class TestCorsWildcardRejected:
    def test_star_origin_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com,*,https://b.example.com")
        monkeypatch.setenv("CACHE_TYPE", "null")
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            _reload_config()


class TestRatelimitStorageResolution:
    def test_explicit_storage_uri_wins(self, monkeypatch):
        monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://custom:6379/1")
        monkeypatch.setenv("CACHE_TYPE", "null")
        monkeypatch.setattr(
            "socket.create_connection",
            MagicMock(side_effect=OSError("redis down")),
        )
        cfg = _reload_config()
        assert cfg.Config.RATELIMIT_STORAGE_URI == "redis://custom:6379/1"

    def test_redis_url_used_when_reachable(self, monkeypatch):
        monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("CACHE_TYPE", "null")
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"+PONG\r\n"
        monkeypatch.setattr(
            "socket.create_connection",
            lambda *_args, **_kwargs: MagicMock(
                __enter__=lambda _s: mock_sock,
                __exit__=lambda *_a: None,
            ),
        )
        cfg = _reload_config()
        assert cfg.Config.RATELIMIT_STORAGE_URI == "redis://localhost:6379/0"

    def test_memory_fallback_when_no_redis(self, monkeypatch):
        monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("CACHE_TYPE", "null")
        monkeypatch.setattr(
            "socket.create_connection",
            MagicMock(side_effect=OSError("redis down")),
        )
        cfg = _reload_config()
        assert cfg.Config.RATELIMIT_STORAGE_URI == "memory://"


class TestNonPostgresSkipsPoolAndBinds:
    def test_sqlite_has_no_pool_size_or_reporting_bind(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("CACHE_TYPE", "null")
        cfg = _reload_config()
        assert cfg.Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite")
        assert "pool_size" not in cfg.Config.SQLALCHEMY_ENGINE_OPTIONS
        assert "max_overflow" not in cfg.Config.SQLALCHEMY_ENGINE_OPTIONS
        assert "reporting" not in cfg.Config.SQLALCHEMY_BINDS


class TestCompanyAddressEnPassthrough:
    def test_explicit_address_en_skips_derivation(self, monkeypatch):
        monkeypatch.setenv("COMPANY_ADDRESS", "فلسطين - رام الله | Palestine - Ramallah")
        monkeypatch.setenv("COMPANY_ADDRESS_EN", "Custom English Address")
        monkeypatch.setenv("CACHE_TYPE", "null")
        cfg = _reload_config()
        assert cfg.Config.COMPANY_ADDRESS_EN == "Custom English Address"
