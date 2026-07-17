from extensions import db
from datetime import datetime, timezone
import secrets


class APIKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    secret = db.Column(db.String(128))
    service = db.Column(db.String(50), nullable=False)
    scope = db.Column(db.String(20), default="write", index=True)  # 'read' | 'write'
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    last_used = db.Column(db.DateTime)
    usage_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    creator = db.relationship("User", backref="api_keys_created")

    @staticmethod
    def generate_key():
        return secrets.token_urlsafe(32)

    def __repr__(self):
        return f"<APIKey {self.service} - {self.name}>"
