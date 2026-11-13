"""Tenant secrets — encrypted key/value store for integration credentials.

Used for ZATCA Phase 2 (CSID, certificate, private key) and the Israel Tax
Authority OAuth access token. Values are Fernet-encrypted at rest with a key
derived from the ``TENANT_SECRETS_KEY`` environment variable (falling back to
``CARD_ENCRYPTION_KEY`` for deployments that already provision it). Secrets
are write-only from the settings UI: the page can say *that* a secret is
set, never show it.
"""

from datetime import UTC, datetime

from extensions import db


class TenantSecret(db.Model):
    __tablename__ = "tenant_secrets"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_tenant_secret_name"),
        db.Index("idx_tenant_secrets_tenant", "tenant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(60), nullable=False)
    ciphertext = db.Column(db.LargeBinary, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id], backref=db.backref("secrets", lazy="dynamic"))

    def __repr__(self):
        return f"<TenantSecret {self.name} tenant={self.tenant_id}>"
