"""Streaming AES-256-GCM backup encryption.

Backup archives are encrypted with AES-256-GCM. The key is derived from
BACKUP_ENCRYPTION_KEY via PBKDF2-HMAC-SHA256. Each archive gets a fresh 96-bit
nonce written to the output file header, followed by the ciphertext and the
128-bit authentication tag.

If BACKUP_ENCRYPTION_KEY is not configured, encryption helpers return the
original path and a no-op wrapper is used so existing unencrypted backups keep
working.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
SALT_LEN = 16
ITERATIONS = 100_000
CHUNK_SIZE = 1024 * 1024  # 1 MiB chunks


class BackupCryptoError(Exception):
    """Raised when backup encryption or decryption fails."""


class BackupCrypto:
    """Encrypt/decrypt backup archives using AES-256-GCM."""

    def __init__(self, key: bytes | str | None = None):
        """Initialize with a raw 32-byte key or a passphrase.

        If ``key`` is a string, it is treated as a passphrase and stretched
        with PBKDF2. If ``key`` is exactly 32 bytes, it is used directly.
        """
        self._raw_key = key
        if key is None:
            env_key = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
            if env_key:
                key = env_key
            else:
                self._key: bytes | None = None
                return

        if isinstance(key, str):
            # Use PBKDF2 to stretch a passphrase into a 256-bit key.
            salt = hashlib.sha256(b"azad-backup-salt-v1").digest()[:SALT_LEN]
            self._key = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, ITERATIONS, dklen=KEY_LEN)
        elif isinstance(key, bytes) and len(key) == KEY_LEN:
            self._key = key
        else:
            raise BackupCryptoError("Backup encryption key must be a 32-byte key or a passphrase string")

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def encrypt_file(self, src_path: str | Path, dest_path: str | Path) -> str:
        """Encrypt ``src_path`` to ``dest_path`` and return the destination path."""
        src = Path(src_path)
        dest = Path(dest_path)
        if not self._key:
            # No encryption configured: copy the file so callers always receive
            # a file at the expected destination.
            import shutil

            shutil.copy2(src, dest)
            return str(dest)

        nonce = os.urandom(NONCE_LEN)
        cipher = Cipher(algorithms.AES(self._key), modes.GCM(nonce))
        encryptor = cipher.encryptor()

        with open(src, "rb") as fin, open(dest, "wb") as fout:
            fout.write(nonce)
            while True:
                chunk = fin.read(CHUNK_SIZE)
                if not chunk:
                    break
                fout.write(encryptor.update(chunk))
            fout.write(encryptor.finalize())
            fout.write(encryptor.tag)

        return str(dest)

    def decrypt_file(self, src_path: str | Path, dest_path: str | Path) -> str:
        """Decrypt ``src_path`` to ``dest_path`` and return the destination path."""
        src = Path(src_path)
        dest = Path(dest_path)
        if not self._key:
            import shutil

            shutil.copy2(src, dest)
            return str(dest)

        file_size = src.stat().st_size
        if file_size < NONCE_LEN + TAG_LEN:
            raise BackupCryptoError("Encrypted backup file is too small to be valid")

        with open(src, "rb") as fin, open(dest, "wb") as fout:
            nonce = fin.read(NONCE_LEN)
            ciphertext_len = file_size - NONCE_LEN - TAG_LEN
            cipher = Cipher(algorithms.AES(self._key), modes.GCM(nonce))
            decryptor = cipher.decryptor()

            remaining = ciphertext_len
            while remaining > 0:
                chunk = fin.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                fout.write(decryptor.update(chunk))
                remaining -= len(chunk)

            tag = fin.read(TAG_LEN)
            try:
                fout.write(decryptor.finalize_with_tag(tag))
            except Exception as exc:
                raise BackupCryptoError("Backup decryption failed (wrong key or corrupt file)") from exc

        return str(dest)

    def encrypted_suffix(self) -> str:
        """Return the filename suffix for encrypted archives."""
        return ".enc" if self.enabled else ""


def get_backup_crypto() -> BackupCrypto:
    """Factory returning a BackupCrypto instance from environment/config."""
    return BackupCrypto()
