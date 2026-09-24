"""advanced AI training: batches, progress mastery, knowledge graph

Creates tables backing the advanced training system:
- ai_training_batches (JSON/Excel import tracking per tenant)
- ai_training_progress (concept coverage + mastery scores per tenant)
- ai_knowledge_graph (concept relationships for gap detection)
"""

import sqlalchemy as sa
from alembic import op

revision = "d1e6f4a2b8c3"
down_revision = "b8c4d2e1a5f6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_training_batches"):
        op.create_table(
            "ai_training_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("source_file", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Index("ix_ai_training_batches_tenant", "tenant_id"),
            sa.Index("ix_ai_training_batches_status", "status"),
        )

    if not inspector.has_table("ai_training_progress"):
        op.create_table(
            "ai_training_progress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("domain", sa.String(length=100), nullable=False),
            sa.Column("topic", sa.String(length=200), nullable=False),
            sa.Column("concept_name", sa.String(length=200), nullable=False),
            sa.Column("covered", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0.0000"),
            sa.Column("mastery_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("learning_velocity", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0.0000"),
            sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Index("ix_ai_training_progress_tenant", "tenant_id"),
            sa.Index("ix_ai_training_progress_domain", "domain"),
            sa.UniqueConstraint("tenant_id", "concept_name", name="uq_training_progress_tenant_concept"),
        )

    if not inspector.has_table("ai_knowledge_graph"):
        op.create_table(
            "ai_knowledge_graph",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("source_concept", sa.String(length=200), nullable=False),
            sa.Column("target_concept", sa.String(length=200), nullable=False),
            sa.Column("relationship_type", sa.String(length=50), nullable=False),
            sa.Column("strength", sa.Numeric(precision=5, scale=4), nullable=False, server_default="1.0000"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Index("ix_ai_knowledge_graph_tenant", "tenant_id"),
        )


def downgrade():
    op.drop_table("ai_knowledge_graph")
    op.drop_table("ai_training_progress")
    op.drop_table("ai_training_batches")
