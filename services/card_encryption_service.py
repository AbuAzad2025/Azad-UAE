"""Card encryption service — handles Fernet encryption/decryption and authorization.

Moves HTTP-layer concerns (config access, owner authorization) out of the
card models so they remain pure ORM.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class CardEncryptionService:
    """Pure encryption/decryption for card data. Callers manage authorization."""

    def __init__(self, encryption_key: str | bytes):
        if not encryption_key:
            raise ValueError("CARD_ENCRYPTION_KEY not configured")
        key_bytes = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        key_bytes = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        self._cipher = Fernet(key_bytes)

    def encrypt(self, data: str | bytes) -> bytes | None:
        """Encrypt string/bytes data. Returns None for empty input."""
        if not data:
            return None
        payload = data.encode() if isinstance(data, str) else data
        return self._cipher.encrypt(payload)

    def decrypt(self, encrypted_data: bytes) -> str | None:
        """Decrypt bytes to string. Returns None for empty input."""
        if not encrypted_data:
            return None
        return self._cipher.decrypt(encrypted_data).decode()

    @staticmethod
    def hash_card(card_number: str) -> str:
        """SHA-256 hash of card number for deduplication/lookup."""
        return hashlib.sha256(str(card_number).encode()).hexdigest()

    @staticmethod
    def detect_card_type(card_number: str) -> str:
        """Detect card type from number prefix."""
        card_str = str(card_number).replace(" ", "").replace("-", "")
        if card_str.startswith("4"):
            return "visa"
        if card_str.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        if card_str.startswith(("34", "37")):
            return "amex"
        if card_str.startswith("6"):
            return "discover"
        return "unknown"
