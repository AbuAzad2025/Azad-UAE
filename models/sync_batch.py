from extensions import db


class SyncBatch(db.Model):
    """Idempotency ledger for external POS stock-sync batches.

    Records are created inside the same atomic_transaction as the stock
    movements they protect.  On rollback the record vanishes, allowing a
    clean retry.
    """

    __tablename__ = "sync_batches"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    idempotency_key = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending | completed | failed
    payload_hash = db.Column(db.String(64))
    processed_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "idempotency_key", name="uq_sync_batch_idempotency"),
        db.Index("ix_sync_batch_tenant_status", "tenant_id", "status"),
    )
