"""Align AI training/knowledge-graph indexes with the SQLAlchemy models.

The models declare ``index=True`` on three columns whose creation migration
only added tenant/status/domain indexes. Fresh ``create_all()`` databases get
all three, while migrated databases are missing them. This revision brings
migrated schemas to the same shape without touching data.

Revision is idempotent: an index that already exists is left alone.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p6q7r8s9t0u1"
down_revision = "n4p5q6r7s8t9"
branch_labels = None
depends_on = None

INDEXES = (
    ("ai_training_batches", "ix_ai_training_batches_created_at", "created_at"),
    ("ai_training_progress", "ix_ai_training_progress_updated_at", "updated_at"),
    ("ai_knowledge_graph", "ix_ai_knowledge_graph_created_at", "created_at"),
)


def _existing(conn) -> set[str]:
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    return {
        index["name"]
        for table, _, _ in INDEXES
        if table in tables
        for index in inspector.get_indexes(table)
        if index.get("name")
    }


def upgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    tables = set(sa.inspect(conn).get_table_names())
    for table, name, column in INDEXES:
        if table not in tables or name in present:
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_index(name, [column], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    tables = set(sa.inspect(conn).get_table_names())
    for table, name, _column in INDEXES:
        if table not in tables or name not in present:
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_index(name)
