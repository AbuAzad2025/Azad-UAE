import os
import pytest
from unittest.mock import patch, MagicMock
from utils.bootstrap_keys import ensure_secret_key, ensure_card_encryption_key, bootstrap_keys

class TestEnsureSecretKey:
    def test_returns_env_value_when_set(self):
        result = ensure_secret_key("/tmp", env_value="existing_key_123")
        assert result == "existing_key_123"
    def test_reads_from_file_when_no_env(self, tmp_path):
        secret_file = tmp_path / "secret_key"
        secret_file.write_text("file_key_456", encoding="utf-8")
        result = ensure_secret_key(str(tmp_path), env_value=None)
        assert result == "file_key_456"
    def test_generates_new_key_when_nothing_exists(self, tmp_path):
        result = ensure_secret_key(str(tmp_path), env_value=None)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
    def test_writes_generated_key_to_file(self, tmp_path):
        secret_file = tmp_path / "secret_key"
        assert not secret_file.exists()
        result = ensure_secret_key(str(tmp_path), env_value=None)
        assert secret_file.exists()
        assert secret_file.read_text(encoding="utf-8") == result
    def test_returns_env_even_if_file_exists(self, tmp_path):
        secret_file = tmp_path / "secret_key"
        secret_file.write_text("file_key", encoding="utf-8")
        result = ensure_secret_key(str(tmp_path), env_value="env_key")
        assert result == "env_key"

class TestEnsureCardEncryptionKey:
    def test_returns_env_value_when_set(self):
        result = ensure_card_encryption_key("/tmp", env_value="card_env_key")
        assert result == "card_env_key"
    def test_reads_from_file_when_no_env(self, tmp_path):
        key_file = tmp_path / ".card_encryption_key"
        key_file.write_text("card_file_key", encoding="utf-8")
        result = ensure_card_encryption_key(str(tmp_path), env_value=None)
        assert result == "card_file_key"
    def test_generates_new_key_when_nothing_exists(self, tmp_path):
        result = ensure_card_encryption_key(str(tmp_path), env_value=None)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
    def test_writes_generated_key_to_file(self, tmp_path):
        key_file = tmp_path / ".card_encryption_key"
        assert not key_file.exists()
        result = ensure_card_encryption_key(str(tmp_path), env_value=None)
        assert key_file.exists()
        assert key_file.read_text(encoding="utf-8") == result

class TestBootstrapKeys:
    def test_updates_app_config(self, tmp_path):
        app = MagicMock()
        app.config = {"SECRET_KEY": "", "CARD_ENCRYPTION_KEY": ""}
        bootstrap_keys(app, str(tmp_path))
        assert len(app.config["SECRET_KEY"]) == 64
        assert len(app.config["CARD_ENCRYPTION_KEY"]) == 64
        assert app.config["SECRET_KEY"] != ""
        assert app.config["CARD_ENCRYPTION_KEY"] != ""
    def test_preserves_existing_env_values(self, tmp_path):
        app = MagicMock()
        app.config = {"SECRET_KEY": "preset_secret", "CARD_ENCRYPTION_KEY": "preset_card"}
        bootstrap_keys(app, str(tmp_path))
        assert app.config["SECRET_KEY"] == "preset_secret"
        assert app.config["CARD_ENCRYPTION_KEY"] == "preset_card"
    def test_uses_default_instance_dir_when_none(self, tmp_path):
        app = MagicMock()
        app.config = {"SECRET_KEY": "", "CARD_ENCRYPTION_KEY": ""}
        with patch("os.path.join") as mock_join:
            mock_join.return_value = str(tmp_path)
            bootstrap_keys(app, None)
        assert len(app.config["SECRET_KEY"]) == 64
