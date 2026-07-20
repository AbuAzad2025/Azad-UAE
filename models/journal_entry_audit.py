from datetime import datetime, timezone
from extensions import db


class JournalEntryAudit(db.Model):
    """سجل تدقيق القيود المحاسبية"""

    __tablename__ = "journal_entry_audits"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("gl_journal_entries.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    old_values = db.Column(db.Text)
    new_values = db.Column(db.Text)
    reason = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    performed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)

    journal_entry = db.relationship("GLJournalEntry")
    user = db.relationship("User")

    def __repr__(self):
        return f"<JournalEntryAudit {self.action} - {self.journal_entry_id}>"
