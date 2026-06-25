from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from utils.bootstrap_keys import (
    bootstrap_keys,
    ensure_card_encryption_key,
    ensure_secret_key,
)


class TestEnsureSecretKey:
    def test_returns_env_value(self, tmp_path):
        assert ensure_secret_key(str(tmp_path), 'from-env') == 'from-env'

    def test_reads_existing_file(self, tmp_path):
        secret_file = tmp_path / 'secret_key'
        secret_file.write_text('  stored-key  ', encoding='utf-8')
        assert ensure_secret_key(str(tmp_path), None) == 'stored-key'

    def test_generates_when_missing(self, tmp_path):
        key = ensure_secret_key(str(tmp_path), None)
        assert len(key) == 64
        assert (tmp_path / 'secret_key').read_text(encoding='utf-8') == key

    def test_read_failure_generates_new(self, tmp_path):
        secret_file = tmp_path / 'secret_key'
        secret_file.write_text('broken', encoding='utf-8')
        with patch('builtins.open', side_effect=OSError('denied')):
            key = ensure_secret_key(str(tmp_path), None)
        assert len(key) == 64

    def test_write_failure_still_returns_key(self, tmp_path):
        with patch('os.makedirs', side_effect=OSError('denied')):
            key = ensure_secret_key(str(tmp_path), None)
        assert len(key) == 64


class TestEnsureCardEncryptionKey:
    def test_returns_env_value(self, tmp_path):
        assert ensure_card_encryption_key(str(tmp_path), 'card-env') == 'card-env'

    def test_reads_existing_file(self, tmp_path):
        key_path = tmp_path / '.card_encryption_key'
        key_path.write_text('card-stored', encoding='utf-8')
        assert ensure_card_encryption_key(str(tmp_path), None) == 'card-stored'

    def test_generates_when_missing(self, tmp_path):
        key = ensure_card_encryption_key(str(tmp_path), None)
        assert len(key) == 64
        assert (tmp_path / '.card_encryption_key').read_text(encoding='utf-8') == key

    def test_read_failure_generates_new(self, tmp_path):
        key_path = tmp_path / '.card_encryption_key'
        key_path.write_text('x', encoding='utf-8')
        with patch('builtins.open', side_effect=OSError('denied')):
            key = ensure_card_encryption_key(str(tmp_path), None)
        assert len(key) == 64

    def test_write_failure_still_returns_key(self, tmp_path):
        with patch('os.makedirs', side_effect=OSError('denied')):
            key = ensure_card_encryption_key(str(tmp_path), None)
        assert len(key) == 64


class TestBootstrapKeys:
    def test_sets_app_config_from_env(self, tmp_path):
        app = MagicMock()
        app.config = {'SECRET_KEY': 'sec', 'CARD_ENCRYPTION_KEY': 'card'}
        bootstrap_keys(app, instance_dir=str(tmp_path))
        assert app.config['SECRET_KEY'] == 'sec'
        assert app.config['CARD_ENCRYPTION_KEY'] == 'card'

    def test_default_instance_dir(self, tmp_path, monkeypatch):
        app = MagicMock()
        app.config = {}
        with patch('utils.bootstrap_keys.ensure_secret_key', return_value='s') as sec, \
             patch('utils.bootstrap_keys.ensure_card_encryption_key', return_value='c') as card:
            bootstrap_keys(app, instance_dir=None)
        assert sec.called
        assert card.called
        assert app.config['SECRET_KEY'] == 's'
        assert app.config['CARD_ENCRYPTION_KEY'] == 'c'

    def test_persists_generated_keys(self, tmp_path):
        app = MagicMock()
        app.config = {}
        bootstrap_keys(app, instance_dir=str(tmp_path))
        assert len(app.config['SECRET_KEY']) == 64
        assert len(app.config['CARD_ENCRYPTION_KEY']) == 64
        assert os.path.exists(os.path.join(str(tmp_path), 'secret_key'))
        assert os.path.exists(os.path.join(str(tmp_path), '.card_encryption_key'))
