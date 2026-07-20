"""
نموذج الترقيم الذكي للمستندات - Smart Document Sequencing
Inspired by Odoo's ir.sequence
"""

from datetime import datetime, timezone
from extensions import db


class DocumentSequence(db.Model):
    """
    Defines a reusable document numbering pattern with atomic counters.
    Patterns support: {prefix}, {year}, {month}, {day}, {branch}, {tenant}, {counter:04d}
    """

    __tablename__ = "document_sequences"
    __table_args__ = (db.UniqueConstraint("tenant_id", "code", name="uq_doc_seq_tenant_code"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))

    # Pattern template, e.g. "INV/{year}/{branch}/{counter:04d}"
    pattern = db.Column(db.String(200), nullable=False, default="{prefix}-{year}-{counter:04d}")
    prefix = db.Column(db.String(20), nullable=False, default="DOC")

    counter = db.Column(db.Integer, nullable=False, default=1)
    counter_reset = db.Column(db.String(20), nullable=False, default="year")  # never, yearly, monthly, daily

    branch_scoped = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Meta
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", backref="document_sequences", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<DocumentSequence {self.code} {self.pattern}>"

    def get_next_number(self, branch_code=None, date=None):
        """
        Generate the next document number based on pattern, counter, and date.
        Must be called inside a transaction with SELECT FOR UPDATE on this row.
        """

        date = date or datetime.now(timezone.utc)

        # Determine if counter should reset
        last_reset = self._get_last_reset_date()
        current_period = self._get_period_key(date)
        if last_reset != current_period and self.counter_reset != "never":
            self.counter = 1

        # Build context
        ctx = {
            "prefix": self.prefix,
            "year": date.strftime("%Y"),
            "month": date.strftime("%m"),
            "day": date.strftime("%d"),
            "branch": branch_code or "",
            "tenant": str(self.tenant_id) if self.tenant_id else "",
            "counter": self.counter,
        }

        pattern = self.pattern
        for pad in [2, 3, 4, 5, 6]:
            placeholder = f"{{counter:0{pad}d}}"
            if placeholder in pattern:
                pattern = pattern.replace(placeholder, f"{self.counter:0{pad}d}")
                break
        else:
            pattern = pattern.replace("{counter}", str(self.counter))

        for key, val in ctx.items():
            if key != "counter":
                pattern = pattern.replace(f"{{{key}}}", str(val))

        # Increment atomically (caller must hold lock)
        self.counter += 1
        return pattern

    def _get_last_reset_date(self):
        """Infer last reset period from updated_at or created_at."""
        dt = self.updated_at or self.created_at
        if not dt:
            return ""
        return self._get_period_key(dt)

    def _get_period_key(self, date):
        if self.counter_reset == "year":
            return date.strftime("%Y")
        elif self.counter_reset == "monthly":
            return date.strftime("%Y-%m")
        elif self.counter_reset == "daily":
            return date.strftime("%Y-%m-%d")
        return ""
