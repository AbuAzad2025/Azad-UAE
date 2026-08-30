"""sale rep name and set null F-06

Revision ID: 17fca8d581b2
Revises: e4506d215617
Create Date: 2026-08-31

F-06: Make sales_rep_id SET NULL and add sales_rep_name text.
Ownership remains seller_id; rep is optional (FK or text), defaults to seller.
"""

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "17fca8d581b2"
down_revision = "e4506d215617"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _fk_exists(table: str, fk_name: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        fks = insp.get_foreign_keys(table)
        return any(fk["name"] == fk_name for fk in fks)
    except Exception:
        return False


def upgrade():
    # Add sales_rep_name
    if not _column_exists("sales", "sales_rep_name"):
        with op.batch_alter_table("sales", schema=None) as batch_op:
            batch_op.add_column(sa.Column("sales_rep_name", sa.String(length=200), nullable=True))

    # Change sales_rep_id FK ondelete to SET NULL (if currently RESTRICT)
    # We need to drop and recreate FK. Name is auto-generated; find it.
    # For batch mode, we can drop constraint if exists and recreate.
    # Use batch alter to handle.
    if _column_exists("sales", "sales_rep_id"):
        # Check if FK exists with RESTRICT - we will recreate as SET NULL
        # In batch mode, alter the FK by dropping and adding
        with op.batch_alter_table("sales", schema=None) as batch_op:
            # Drop old FK if exists (name may vary)
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("sales_sales_rep_id_fkey", type_="foreignkey")
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_sales_sales_rep_id_users", type_="foreignkey")
            # Recreate with SET NULL
            # Only create if not already exists with correct ondelete
            # We attempt to create; if fails due to existing, suppress
            with contextlib.suppress(Exception):
                batch_op.create_foreign_key(
                    "fk_sales_sales_rep_id_users",
                    "users",
                    ["sales_rep_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade():
    if _column_exists("sales", "sales_rep_name"):
        with op.batch_alter_table("sales", schema=None) as batch_op:
            batch_op.drop_column("sales_rep_name")

    # Revert FK to RESTRICT
    if _column_exists("sales", "sales_rep_id"):
        with op.batch_alter_table("sales", schema=None) as batch_op:
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_sales_sales_rep_id_users", type_="foreignkey")
            with contextlib.suppress(Exception):
                batch_op.create_foreign_key(
                    "fk_sales_sales_rep_id_users",
                    "users",
                    ["sales_rep_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
