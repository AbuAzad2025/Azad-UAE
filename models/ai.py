"""AI system models — memories, interactions, expertise with tenant isolation."""
from datetime import datetime, timezone
from extensions import db


class AiMemory(db.Model):
    __tablename__ = "ai_memories"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    category = db.Column(db.String(50), nullable=False, default="general", index=True)
    key = db.Column(db.String(255), nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    confidence = db.Column(db.Numeric(3, 2), nullable=False, default=0.80)
    source = db.Column(db.String(100), nullable=True)
    access_count = db.Column(db.Integer, nullable=False, default=0)
    last_accessed = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    tenant = db.relationship('Tenant', backref='ai_memories', foreign_keys=[tenant_id])

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "confidence": float(self.confidence) if self.confidence else 0.80,
            "source": self.source,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AiInteraction(db.Model):
    __tablename__ = "ai_interactions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = db.Column(db.String(100), nullable=True, index=True)
    query = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=True)
    intent = db.Column(db.String(100), nullable=True)
    was_successful = db.Column(db.Boolean, nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)
    is_training_sample = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    tenant = db.relationship('Tenant', backref='ai_interactions', foreign_keys=[tenant_id])
    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "query": self.query,
            "response": self.response,
            "intent": self.intent,
            "was_successful": self.was_successful,
            "response_time_ms": self.response_time_ms,
            "is_training_sample": self.is_training_sample,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AiExpertise(db.Model):
    __tablename__ = "ai_expertise"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    domain = db.Column(db.String(100), nullable=False, index=True)
    topic = db.Column(db.String(200), nullable=False)
    knowledge = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=5)
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    tenant = db.relationship('Tenant', backref='ai_expertise', foreign_keys=[tenant_id])

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "topic": self.topic,
            "knowledge": self.knowledge,
            "priority": self.priority,
            "usage_count": self.usage_count,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
