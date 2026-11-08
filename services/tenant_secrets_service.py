"""Tenant secrets — encrypted storage for integration credentials.

Fernet-encrypted at rest, keyed off ``TENANT_SECRETS_KEY`` (falling back to
``CARD_ENCRYPTION_KEY``). Secrets are write-only: UI shows *whether* a
secret is set, never its value. Reading happens only inside integration
code paths, never in templates.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet

from extensions import db

logger = logging.getLogger(__name__)


def _key_bytes() -> bytes:
    key = os.environ.get("TENANT_SECRETS_KEY") or os.environ.get("CARD_ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "TENANT_SECRETS_KEY is not configured — encrypted tenant secrets (ZATCA CSID, ITA token) cannot be stored."
        )
    return base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())


class TenantSecretsService:
    """Fernet-encrypted per-tenant key/value store."""

    @staticmethod
    def set(tenant_id: int, name: str, value: str, *, user_id: int | None = None) -> None:
        from models import TenantSecret

        payload = Fernet(_key_bytes()).encrypt(value.encode("utf-8"))
        row = TenantSecret.query.filter_by(tenant_id=int(tenant_id), name=name).first()
        if row is not None:
            row.ciphertext = payload
            row.created_by = user_id
        else:
            row = TenantSecret(tenant_id=int(tenant_id), name=name, ciphertext=payload, created_by=user_id)
            db.session.add(row)
        db.session.flush()

    @staticmethod
    def get(tenant_id: int, name: str) -> str | None:
        from models import TenantSecret

        row = TenantSecret.query.filter_by(tenant_id=int(tenant_id), name=name).first()
        if row is None:
            return None
        try:
            return Fernet(_key_bytes()).decrypt(row.ciphertext).decode("utf-8")
        except Exception:
            logger.error("Failed to decrypt tenant secret %r for tenant %s", name, tenant_id)
            return None

    @staticmethod
    def delete(tenant_id: int, name: str) -> None:
        from models import TenantSecret

        TenantSecret.query.filter_by(tenant_id=int(tenant_id), name=name).delete()

    @staticmethod
    def is_set(tenant_id: int, name: str) -> bool:
        from models import TenantSecret

        return TenantSecret.query.filter_by(tenant_id=int(tenant_id), name=name).first() is not None

    @staticmethod
    def clear(tenant_id: int, name: str) -> None:
        TenantSecretsService.delete(tenant_id, name)
