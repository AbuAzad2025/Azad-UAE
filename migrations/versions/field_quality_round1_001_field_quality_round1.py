"""field_quality_round1

Revision ID: field_quality_round1
Revises: perf_idx_round1_001
Create Date: 2026-06-01 14:00:00.000000

Safe widening of phone columns and NOT NULL alignment for boolean drift columns.
Does not change UNIQUE constraints, tenant_id nullability, or status CHECK constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "field_quality_round1"
down_revision = "perf_idx_round1_001"
branch_labels = None
depends_on = None

PHONE_COLUMNS = [
    ("customers", "phone"),
    ("users", "phone"),
    ("suppliers", "phone"),
    ("branches", "phone"),
    ("employees", "phone"),
]


def _has_column(conn, table: str, column: str) -> bool:
    insp = inspect(conn)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    conn = op.get_bind()
    for table, column in PHONE_COLUMNS:
        if _has_column(conn, table, column):
            op.alter_column(
                table,
                column,
                existing_type=sa.String(20),
                type_=sa.String(50),
                existing_nullable=True,
            )

    if _has_column(conn, "products", "has_serial_number"):
        op.execute(
            sa.text(
                "UPDATE products SET has_serial_number = false WHERE has_serial_number IS NULL"
            )
        )
        op.alter_column(
            "products",
            "has_serial_number",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        )

    if _has_column(conn, "donations", "gl_posted"):
        op.execute(
            sa.text("UPDATE donations SET gl_posted = false WHERE gl_posted IS NULL")
        )
        op.alter_column(
            "donations",
            "gl_posted",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        )


def downgrade():
    conn = op.get_bind()
    for table, column in PHONE_COLUMNS:
        if _has_column(conn, table, column):
            op.alter_column(
                table,
                column,
                existing_type=sa.String(50),
                type_=sa.String(20),
                existing_nullable=True,
            )

    if _has_column(conn, "products", "has_serial_number"):
        op.alter_column(
            "products",
            "has_serial_number",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )

    if _has_column(conn, "donations", "gl_posted"):
        op.alter_column(
            "donations",
            "gl_posted",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
