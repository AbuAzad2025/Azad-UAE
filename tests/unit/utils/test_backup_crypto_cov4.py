"""Cov4: backup_crypto uncovered arcs — env key, decrypt passthrough, tiny file, factory."""

from __future__ import annotations

import os

import pytest

from utils.backup_crypto import BackupCrypto, BackupCryptoError, get_backup_crypto


def test_env_key_bytes_used_directly(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "env-passphrase-xyz")
    c = BackupCrypto()
    assert c.enabled  # line 48-49: env key branch
    assert c.encrypted_suffix() == ".enc"  # line 133


def test_env_absent_disables(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    c = BackupCrypto(None)
    assert not c.enabled  # lines 50-52
    assert c.encrypted_suffix() == ""  # line 133 disabled


def test_raw_32byte_key_used_directly(tmp_path):
    key = os.urandom(32)
    c = BackupCrypto(key)
    assert c.enabled  # lines 58-59
    src = tmp_path / "a.bin"
    src.write_bytes(b"0123456789abcdef" * 100)
    enc = tmp_path / "a.bin.enc"
    dec = tmp_path / "a.bin.dec"
    c.encrypt_file(str(src), str(enc))  # lines 79-93
    c.decrypt_file(str(enc), str(dec))  # lines 105-129
    assert dec.read_bytes() == src.read_bytes()


def test_decrypt_passthrough_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    c = BackupCrypto(None)
    src = tmp_path / "plain.txt"
    src.write_text("plain-data")
    dst = tmp_path / "copy.txt"
    out = c.decrypt_file(str(src), str(dst))  # lines 99-103
    assert out == str(dst)
    assert dst.read_text() == "plain-data"


def test_decrypt_too_small_raises(tmp_path):
    c = BackupCrypto("some-passphrase-for-test")
    tiny = tmp_path / "tiny.enc"
    tiny.write_bytes(b"short")
    with pytest.raises(BackupCryptoError, match="too small"):  # line 106-107
        c.decrypt_file(str(tiny), str(tmp_path / "out.bin"))


def test_decrypt_corrupt_tag_raises(tmp_path):
    c = BackupCrypto("another-passphrase-value")
    src = tmp_path / "s.bin"
    src.write_bytes(b"hello world data here" * 50)
    enc = tmp_path / "s.bin.enc"
    c.encrypt_file(str(src), str(enc))
    raw = bytearray(enc.read_bytes())
    raw[-1] ^= 0xFF  # corrupt tag -> lines 124-127
    enc.write_bytes(bytes(raw))
    with pytest.raises(BackupCryptoError, match="wrong key or corrupt"):
        c.decrypt_file(str(enc), str(tmp_path / "bad.bin"))


def test_get_backup_crypto_factory(monkeypatch):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    c = get_backup_crypto()  # line 136-138
    assert isinstance(c, BackupCrypto)
    assert not c.enabled
