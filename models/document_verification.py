"""
Document Verification — unique hash + public token for QR-barcode traceability.
Each document gets one immutable verification record, tenant-scoped,
with pre-generation collision check (The Spell).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from extensions import db


class DocumentVerification(db.Model):
    __tablename__ = "document_verifications"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)
    document_id = db.Column(db.Integer, nullable=False)
    document_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    public_token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    __table_args__ = (
        db.Index("ix_docver_tenant_doc", "tenant_id", "document_type", "document_id", unique=True),
    )

    @staticmethod
    def _generate_hash(tenant_id, document_type, document_id):
        raw = f"{tenant_id}:{document_type}:{document_id}:{uuid.uuid4().hex}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _generate_token():
        return uuid.uuid4().hex

    @classmethod
    def get_or_create(cls, tenant_id, document_type, document_id, created_by=None):
        existing = cls.query.filter_by(
            tenant_id=tenant_id, document_type=document_type, document_id=document_id
        ).first()
        if existing:
            return existing

        for _ in range(10):
            candidate = cls._generate_hash(tenant_id, document_type, document_id)
            collision = cls.query.filter_by(document_hash=candidate).first()
            if not collision:
                token = cls._generate_token()
                rec = cls(
                    tenant_id=tenant_id,
                    document_type=document_type,
                    document_id=document_id,
                    document_hash=candidate,
                    public_token=token,
                    created_by=created_by,
                )
                db.session.add(rec)
                return rec

        raise RuntimeError("Failed to generate unique document hash after 10 attempts")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "document_type": self.document_type,
            "document_id": self.document_id,
            "document_hash": self.document_hash,
            "public_token": self.public_token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
