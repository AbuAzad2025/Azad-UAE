"""add AI interaction telemetry columns to ai_interactions

Revision ID: b81e7a2c41d0
Revises: dd28ea3aa6cc
Create Date: 2026-09-05

Master Directive Phase 4 (observability): record which native tools the
assistant executed (tool_names), which fallback path produced the answer
(fallback_path: native_tools / legacy_action / local / streamed_*), and the
model confidence when known. All columns are nullable so historical rows and
offline test databases keep working unchanged.
"""

import sqlalchemy as sa
from alembic import op

revision = "b81e7a2c41d0"
down_revision = "dd28ea3aa6cc"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False


def upgrade():
    if not _column_exists("ai_interactions", "tool_names"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("tool_names", sa.Text(), nullable=True))
    if not _column_exists("ai_interactions", "fallback_path"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("fallback_path", sa.String(50), nullable=True))
    if not _column_exists("ai_interactions", "confidence"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("confidence", sa.Numeric(3, 2), nullable=True))


def downgrade():
    if _column_exists("ai_interactions", "confidence"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.drop_column("confidence")
    if _column_exists("ai_interactions", "fallback_path"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.drop_column("fallback_path")
    if _column_exists("ai_interactions", "tool_names"):
        with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
            batch_op.drop_column("tool_names")
