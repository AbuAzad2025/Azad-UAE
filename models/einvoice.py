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

    __table_args__ = (db.Index("idx_einvoice_tenant_created", "tenant_id", "created_at"),)

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
    # "invoice" (388) or "credit_note" (381, issued for returns)
    doc_type = db.Column(db.String(20), nullable=False, server_default="invoice", default="invoice")
    # Set when this row is the statutory document of a product return.
    return_id = db.Column(
        db.Integer,
        db.ForeignKey("product_returns.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Israel Tax Authority — allocation number (מספר הקצאה) once requested.
    ita_allocation_number = db.Column(db.String(30))
    # ZATCA Phase 2 chain — set for KSA simplified invoices when the tenant
    # enables Phase 2: counter (1-based).
    invoice_counter_value = db.Column(db.Integer)
    xml_payload = db.Column(db.Text, nullable=False)
    qr_base64 = db.Column(db.Text)
    invoice_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default="generated", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id], backref=db.backref("einvoice", uselist=False))

    def __repr__(self):
        return f"<EInvoice {self.country} sale={self.sale_id} {self.format}>"
