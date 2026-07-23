"""add pos phase4 omnichannel (rma, saas flags, idempotency, cash refunds)

Phase 4 — Omnichannel, Smart Returns (RMA), SaaS Feature Flagging, and
Offline-First Idempotency:

- tenants: enable_pos_promotions / enable_pos_multi_tender /
  enable_pos_returns / enable_pos_shifts (all NULLABLE — NULL inherits the
  plan-level default: pro/enterprise on, basic off; explicit values are
  per-tenant overrides). Existing tenants keep working unchanged.
- pos_sessions / pos_shifts: total_cash_refunds (base currency; additive,
  zero-default) — cash refunds paid out of the drawer for POS returns,
  folded into the expected-balance formula.
- new table: idempotency_keys — durable tenant-scoped idempotency ledger
  for POS write endpoints (checkout, returns, session open/close).

All changes are additive; no existing column is altered.

Revision ID: d4a2b8c91e07
Revises: c9f1e07b3a24
Create Date: 2026-08-03 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4a2b8c91e07"
down_revision = "c9f1e07b3a24"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enable_pos_promotions", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("enable_pos_multi_tender", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("enable_pos_returns", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("enable_pos_shifts", sa.Boolean(), nullable=True))

    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("total_cash_refunds", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )

    with op.batch_alter_table("pos_shifts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("total_cash_refunds", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_keys_scope"),
    )
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_idempotency_keys_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_idempotency_keys_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_idempotency_keys_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_idempotency_keys_created_at"), ["created_at"], unique=False)
        batch_op.create_index("ix_idempotency_keys_tenant_status", ["tenant_id", "status"], unique=False)


def downgrade():
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.drop_index("ix_idempotency_keys_tenant_status")
        batch_op.drop_index(batch_op.f("ix_idempotency_keys_created_at"))
        batch_op.drop_index(batch_op.f("ix_idempotency_keys_status"))
        batch_op.drop_index(batch_op.f("ix_idempotency_keys_user_id"))
        batch_op.drop_index(batch_op.f("ix_idempotency_keys_tenant_id"))
    op.drop_table("idempotency_keys")

    with op.batch_alter_table("pos_shifts", schema=None) as batch_op:
        batch_op.drop_column("total_cash_refunds")

    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.drop_column("total_cash_refunds")

    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("enable_pos_shifts")
        batch_op.drop_column("enable_pos_returns")
        batch_op.drop_column("enable_pos_multi_tender")
        batch_op.drop_column("enable_pos_promotions")
