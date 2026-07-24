"""add pos wave c (fraud signals, fefo stock batches)

- pos_fraud_signals: insert-only, hash-chained POS irregularity log
  (voids, drawer opens) with per-tenant repeat aggregation.
- stock_batches: FEFO lot layer behind the global ``enable_batches``
  toggle — receipt lots with expiry dates consumed soonest-expiry-first.

Revision ID: f7b3a1c82e09
Revises: d4a2b8c91e07
Create Date: 2026-07-24 21:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7b3a1c82e09"
down_revision = "d4a2b8c91e07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pos_fraud_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("repeat_count", sa.Integer(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pos_fraud_signals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_branch_id"), ["branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_session_id"), ["session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_event_type"), ["event_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_entry_hash"), ["entry_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_fraud_signals_created_at"), ["created_at"], unique=False)

    op.create_table(
        "stock_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("stock_batches", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stock_batches_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_stock_batches_product_id"), ["product_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_stock_batches_warehouse_id"), ["warehouse_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_stock_batches_expiry_date"), ["expiry_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_stock_batches_received_at"), ["received_at"], unique=False)


def downgrade():
    with op.batch_alter_table("stock_batches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_batches_received_at"))
        batch_op.drop_index(batch_op.f("ix_stock_batches_expiry_date"))
        batch_op.drop_index(batch_op.f("ix_stock_batches_warehouse_id"))
        batch_op.drop_index(batch_op.f("ix_stock_batches_product_id"))
        batch_op.drop_index(batch_op.f("ix_stock_batches_tenant_id"))
    op.drop_table("stock_batches")

    with op.batch_alter_table("pos_fraud_signals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_created_at"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_entry_hash"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_event_type"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_session_id"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_user_id"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_branch_id"))
        batch_op.drop_index(batch_op.f("ix_pos_fraud_signals_tenant_id"))
    op.drop_table("pos_fraud_signals")
