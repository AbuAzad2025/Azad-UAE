"""add_product_serial_columns

Revision ID: 11c273f17b28
Revises: 5b37cc7276da
Create Date: 2026-03-01 00:33:03.812221

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = '11c273f17b28'
down_revision = '5b37cc7276da'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    expense_indexes = {idx.get("name") for idx in insp.get_indexes("expenses")}
    if "ix_expenses_is_active" not in expense_indexes:
        op.create_index("ix_expenses_is_active", "expenses", ["is_active"], unique=False)

    product_cols = {c.get("name") for c in insp.get_columns("products")}
    with op.batch_alter_table("products", schema=None) as batch_op:
        if "has_serial_number" not in product_cols:
            batch_op.add_column(sa.Column("has_serial_number", sa.Boolean(), nullable=True))
        if "warranty_days" not in product_cols:
            batch_op.add_column(sa.Column("warranty_days", sa.Integer(), nullable=True))

    product_cols = {c.get("name") for c in insp.get_columns("products")}
    if "has_serial_number" in product_cols:
        op.execute(text("UPDATE products SET has_serial_number = FALSE WHERE has_serial_number IS NULL"))
    if "warranty_days" in product_cols:
        op.execute(text("UPDATE products SET warranty_days = 0 WHERE warranty_days IS NULL"))

    if "has_serial_number" in product_cols:
        with op.batch_alter_table("products", schema=None) as batch_op:
            batch_op.alter_column("has_serial_number", nullable=False)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    product_cols = {c.get("name") for c in insp.get_columns("products")}
    with op.batch_alter_table("products", schema=None) as batch_op:
        if "warranty_days" in product_cols:
            batch_op.drop_column("warranty_days")
        if "has_serial_number" in product_cols:
            batch_op.drop_column("has_serial_number")

    expense_indexes = {idx.get("name") for idx in insp.get_indexes("expenses")}
    if "ix_expenses_is_active" in expense_indexes:
        op.drop_index("ix_expenses_is_active", table_name="expenses")
