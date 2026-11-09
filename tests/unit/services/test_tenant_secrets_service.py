"""Unit tests for TenantSecretsService key handling and branches."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.tenant_secrets_service import TenantSecretsService


class TestKey:
    def test_missing_key_raises(self, monkeypatch):
        for name in ("TENANT_SECRETS_KEY", "CARD_ENCRYPTION_KEY", "SECRET_KEY"):
            monkeypatch.delenv(name, raising=False)
        from services import tenant_secrets_service

        with pytest.raises(ValueError, match="TENANT_SECRETS_KEY"):
            tenant_secrets_service._key_bytes()


class TestService:
    def _query(self, mocker, rows):
        secret_model = mocker.patch("models.TenantSecret")
        chain = MagicMock()
        chain.first.return_value = rows
        secret_model.query.filter_by.return_value = chain
        return secret_model, chain

    def test_set_creates(self, mocker, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-key")
        secret_model, chain = self._query(mocker, None)
        secret_model.return_value = MagicMock()
        mock_db = mocker.patch("services.tenant_secrets_service.db")
        TenantSecretsService.set(1, "zatca_csid", "value")
        secret_model.assert_called_once()
        mock_db.session.add.assert_called_once()
        mock_db.session.flush.assert_called_once()

    def test_set_updates_existing(self, mocker, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-key")
        existing = MagicMock(ciphertext=b"old")
        secret_model, chain = self._query(mocker, existing)
        mock_db = mocker.patch("services.tenant_secrets_service.db")
        TenantSecretsService.set(1, "zatca_csid", "value", user_id=4)
        assert existing.ciphertext != b"old"
        assert existing.created_by == 4
        mock_db.session.add.assert_not_called()

    def test_get_missing_returns_none(self, mocker):
        self._query(mocker, None)
        assert TenantSecretsService.get(1, "missing") is None

    def test_get_decrypt_failure_returns_none(self, mocker, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-key")
        self._query(mocker, MagicMock(ciphertext=b"not-fernet"))
        assert TenantSecretsService.get(1, "zatca_csid") is None

    def test_delete_and_clear(self, mocker):
        secret_model, chain = self._query(mocker, MagicMock())
        chain.first.return_value = MagicMock()
        TenantSecretsService.delete(1, "zatca_csid")
        chain.delete.assert_called_once()
        assert TenantSecretsService.is_set(1, "zatca_csid") is True
        TenantSecretsService.clear(1, "zatca_csid")
        assert chain.delete.call_count == 2
