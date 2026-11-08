"""E-invoice artifacts generated for posted sales.

One row per sale, tenant-scoped. The row is the durable record that the
statutory document was produced — it is intentionally not dropped when the
sale is later archived or voided. Government-gateway submission (CSID
onboarding, ZATCA Phase 2 signing, Israel Tax Authority allocation number,
PMA/FTA access points) requires tenant credentials and is performed from
that flow; nothing here marks a document as government-accepted.
"""

from datetime import UTC, datetime

from extensions import db


class EInvoice(db.Model):
    __tablename__ = "e_invoices"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "sale_id", name="uq_einvoice_tenant_sale"),
        db.Index("idx_einvoice_tenant_created", "tenant_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country = db.Column(db.String(2), nullable=False)
    format = db.Column(db.String(50), nullable=False)
    xml_payload = db.Column(db.Text, nullable=False)
    qr_base64 = db.Column(db.Text)
    invoice_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default="generated", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id], backref=db.backref("einvoice", uselist=False))

    def __repr__(self):
        return f"<EInvoice {self.country} sale={self.sale_id} {self.format}>"
