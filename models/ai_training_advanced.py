"""
AI Advanced Training Models — Training batches, progress tracking, and knowledge graph.
"""

from datetime import UTC, datetime

from extensions import db


class AiTrainingBatch(db.Model):
    """Tracks imported training batches (JSON/Excel) with source and processing status."""

    __tablename__ = "ai_training_batches"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_file = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)  # json or excel
    status = db.Column(
        db.String(30), nullable=False, default="pending", index=True
    )  # pending/processing/completed/completed_with_errors/failed
    record_count = db.Column(db.Integer, nullable=False, default=0)
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    tenant = db.relationship("Tenant", backref="ai_training_batches")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source_file": self.source_file,
            "file_type": self.file_type,
            "status": self.status,
            "record_count": self.record_count,
            "processed_count": self.processed_count,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AiTrainingProgress(db.Model):
    """Tenant-level training progress and mastery metrics."""

    __tablename__ = "ai_training_progress"
    __table_args__ = (db.UniqueConstraint("tenant_id", "concept_name", name="uq_training_progress_tenant_concept"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    domain = db.Column(db.String(100), nullable=False, index=True)
    topic = db.Column(db.String(200), nullable=False)
    concept_name = db.Column(db.String(200), nullable=False)
    covered = db.Column(db.Boolean, nullable=False, default=False)
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    confidence = db.Column(db.Numeric(5, 4), nullable=False, default=0.0000)
    mastery_score = db.Column(db.Integer, nullable=False, default=0)
    learning_velocity = db.Column(db.Numeric(5, 4), nullable=False, default=0.0000)
    last_accessed = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        index=True,
    )
    tenant = db.relationship("Tenant", backref="ai_training_progress")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "topic": self.topic,
            "concept_name": self.concept_name,
            "covered": self.covered,
            "usage_count": self.usage_count,
            "confidence": float(self.confidence) if self.confidence else 0.0,
            "mastery_score": self.mastery_score,
            "learning_velocity": float(self.learning_velocity) if self.learning_velocity else 0.0,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AiKnowledgeGraph(db.Model):
    """Concept relationships for advanced reasoning and gap detection."""

    __tablename__ = "ai_knowledge_graph"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_concept = db.Column(db.String(200), nullable=False)
    target_concept = db.Column(db.String(200), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)  # prerequisite, related_to, example_of
    strength = db.Column(db.Numeric(5, 4), nullable=False, default=1.0000)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    tenant = db.relationship("Tenant", backref="ai_knowledge_graph")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source_concept": self.source_concept,
            "target_concept": self.target_concept,
            "relationship_type": self.relationship_type,
            "strength": float(self.strength) if self.strength else 1.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
