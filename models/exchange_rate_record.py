"""
نموذج سجل سعر الصرف - Exchange Rate Record
Phase 6: Exchange Rate Framework
"""

from datetime import datetime, timezone
from extensions import db


class ExchangeRateRecord(db.Model):
    """
    سجل أسعار الصرف المُدخلة يدوياً أو المُستخرجة من API خارجي.
    Each record is immutable after creation (historical rates must not change).
    """

    __tablename__ = "exchange_rate_records"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id",
            "from_currency",
            "to_currency",
            "effective_date",
            name="uq_rate_tenant_pair_date",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_currency = db.Column(db.String(3), nullable=False, index=True)
    to_currency = db.Column(db.String(3), nullable=False, index=True)
    rate = db.Column(db.Numeric(18, 6), nullable=False)

    # Source tracking
    source = db.Column(
        db.String(30), default="manual"
    )  # manual, api_fallback, api_primary
    api_provider = db.Column(db.String(50), nullable=True)
    api_response_id = db.Column(db.String(100), nullable=True)

    # Effective date (rate is valid for this calendar day)
    effective_date = db.Column(db.Date, nullable=False, index=True)

    locked_by_document_type = db.Column(db.String(50), nullable=True)
    locked_by_document_id = db.Column(db.Integer, nullable=True)

    # Audit
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    tenant = db.relationship(
        "Tenant", backref="exchange_rate_records", foreign_keys=[tenant_id]
    )
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<ExchangeRate {self.from_currency}->{self.to_currency} {self.rate} ({self.effective_date})>"
