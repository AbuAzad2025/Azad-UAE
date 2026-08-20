"""Tests for utils.backup_crypto."""

import os
from pathlib import Path

import pytest

from utils.backup_crypto import BackupCrypto, BackupCryptoError


@pytest.fixture
def sample_file(tmp_path: Path) -> str:
    path = tmp_path / "sample.txt"
    path.write_text("hello backup world")
    return str(path)


class TestBackupCrypto:
    def test_disabled_when_no_key(self, tmp_path: Path, sample_file: str):
        crypto = BackupCrypto(None)
        assert not crypto.enabled
        dest = tmp_path / "out.txt"
        result = crypto.encrypt_file(sample_file, str(dest))
        assert result == str(dest)
        assert dest.read_text() == "hello backup world"

    def test_round_trip_with_passphrase(self, tmp_path: Path, sample_file: str):
        crypto = BackupCrypto("super-secret-passphrase")
        assert crypto.enabled
        encrypted = tmp_path / "sample.txt.enc"
        crypto.encrypt_file(sample_file, str(encrypted))
        assert encrypted.exists()
        assert encrypted.read_bytes() != Path(sample_file).read_bytes()

        decrypted = tmp_path / "sample_decrypted.txt"
        crypto.decrypt_file(str(encrypted), str(decrypted))
        assert decrypted.read_text() == "hello backup world"

    def test_wrong_passphrase_fails(self, tmp_path: Path, sample_file: str):
        crypto = BackupCrypto("correct-passphrase")
        encrypted = tmp_path / "sample.txt.enc"
        crypto.encrypt_file(sample_file, str(encrypted))

        wrong_crypto = BackupCrypto("wrong-passphrase")
        decrypted = tmp_path / "sample_decrypted.txt"
        with pytest.raises(BackupCryptoError):
            wrong_crypto.decrypt_file(str(encrypted), str(decrypted))

    def test_large_file_round_trip(self, tmp_path: Path):
        crypto = BackupCrypto("large-file-key")
        src = tmp_path / "large.bin"
        data = os.urandom(5 * 1024 * 1024 + 1234)  # > 5 MiB
        src.write_bytes(data)

        encrypted = tmp_path / "large.bin.enc"
        crypto.encrypt_file(str(src), str(encrypted))

        decrypted = tmp_path / "large_decrypted.bin"
        crypto.decrypt_file(str(encrypted), str(decrypted))
        assert decrypted.read_bytes() == data

    def test_invalid_key_length_raises(self):
        with pytest.raises(BackupCryptoError):
            BackupCrypto(b"too-short")

    def test_encrypted_suffix(self):
        assert BackupCrypto("key").encrypted_suffix() == ".enc"
        assert BackupCrypto(None).encrypted_suffix() == ""
