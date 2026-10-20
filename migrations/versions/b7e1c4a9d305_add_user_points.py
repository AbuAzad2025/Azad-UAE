"""add users.points - persist the gamification balance

The points economy did not work at all. ``services/gamification_service.py``
guarded its write with ``if not hasattr(user, "points")`` and then set
``user.points = (user.points or 0) + points``. The ``users`` table had no
``points`` column, so that assignment created a plain Python attribute on the
ORM instance and was thrown away when the session closed. Every award was a
no-op on disk, and ``get_leaderboard`` - which sorted by
``User.points.desc() if hasattr(User, "points") else User.id`` - fell through
to sorting by id, so the board was simply the oldest users first.

This revision gives the balance a home:

    users.points  INTEGER NOT NULL DEFAULT 0

``DEFAULT 0`` is what makes the ALTER safe on a table that already has rows:
PostgreSQL 11+ stores the default as a "missing value" and does not rewrite
the table, so the migration is instant on a live users table. The default is
kept (not dropped afterwards) so a row inserted outside the ORM still lands on
zero rather than NULL, and so the model and the schema agree.

The leaderboard reads one tenant's active, non-owner users ordered by points
descending. A tenant-leading index that ends on the sort key lets PostgreSQL
walk the index in points order and stop after the first page instead of
sorting the whole tenant:

    idx_users_tenant_points  (tenant_id, points)

Both statements are idempotent - the column and the index are created only
when they are absent - and the downgrade drops exactly what this revision
creates.

Revision ID: b7e1c4a9d305
Revises: d4e5f6a7b8c9
Create Date: 2026-10-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e1c4a9d305"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

TABLE = "users"
COLUMN = "points"
INDEX = "idx_users_tenant_points"


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _index_exists(table: str, index_name: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return index_name in [i["name"] for i in insp.get_indexes(table)]
    except Exception:
        return False


def upgrade() -> None:
    if not _column_exists(TABLE, COLUMN):
        with op.batch_alter_table(TABLE, schema=None) as batch_op:
            batch_op.add_column(sa.Column(COLUMN, sa.Integer(), nullable=False, server_default=sa.text("0")))

    if not _index_exists(TABLE, INDEX):
        with op.batch_alter_table(TABLE, schema=None) as batch_op:
            batch_op.create_index(INDEX, ["tenant_id", COLUMN], unique=False)


def downgrade() -> None:
    if _index_exists(TABLE, INDEX):
        with op.batch_alter_table(TABLE, schema=None) as batch_op:
            batch_op.drop_index(INDEX)

    if _column_exists(TABLE, COLUMN):
        with op.batch_alter_table(TABLE, schema=None) as batch_op:
            batch_op.drop_column(COLUMN)
