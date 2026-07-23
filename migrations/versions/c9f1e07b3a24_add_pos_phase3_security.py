"""add pos phase3 security (sessions, overrides, cash movements)

Phase 3 — Strict Sessions, Shift Security, Manager Overrides, Blind Shift
Closing, Pay-ins/Pay-outs:

- pos_sessions: terminal_id, paused_at, total_change_given, total_pay_ins,
  total_pay_outs (all additive, nullable/zero-default).
- pos_shifts: total_change_given, total_pay_ins, total_pay_outs.
- users: supervisor_pin_hash (nullable).
- new tables: pos_cash_movements, pos_override_tokens.

Revision ID: c9f1e07b3a24
Revises: b4e8d3f02a16
Create Date: 2026-08-02 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9f1e07b3a24"
down_revision = "b4e8d3f02a16"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("terminal_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("paused_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("total_change_given", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )
        batch_op.add_column(
            sa.Column("total_pay_ins", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )
        batch_op.add_column(
            sa.Column("total_pay_outs", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )

    with op.batch_alter_table("pos_shifts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("total_change_given", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )
        batch_op.add_column(
            sa.Column("total_pay_ins", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )
        batch_op.add_column(
            sa.Column("total_pay_outs", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("supervisor_pin_hash", sa.String(length=255), nullable=True))

    op.create_table(
        "pos_cash_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=True),
        sa.Column("authorized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("movement_type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("gl_entry_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["gl_entry_id"], ["gl_journal_entries.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["pos_shifts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pos_cash_movements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pos_cash_movements_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_cash_movements_branch_id"), ["branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_cash_movements_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_cash_movements_session_id"), ["session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_cash_movements_movement_type"), ["movement_type"], unique=False)
        batch_op.create_index("idx_pos_cash_movement_session", ["session_id", "movement_type"], unique=False)
        batch_op.create_index("idx_pos_cash_movement_shift", ["shift_id"], unique=False)

    op.create_table(
        "pos_override_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("cashier_user_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cashier_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supervisor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce", name="uq_pos_override_tokens_nonce"),
    )
    with op.batch_alter_table("pos_override_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pos_override_tokens_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_override_tokens_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_override_tokens_cashier_user_id"), ["cashier_user_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_pos_override_tokens_supervisor_user_id"), ["supervisor_user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_pos_override_tokens_nonce"), ["nonce"], unique=True)
        batch_op.create_index("idx_pos_override_token_cashier", ["cashier_user_id", "action"], unique=False)


def downgrade():
    with op.batch_alter_table("pos_override_tokens", schema=None) as batch_op:
        batch_op.drop_index("idx_pos_override_token_cashier")
        batch_op.drop_index(batch_op.f("ix_pos_override_tokens_nonce"))
        batch_op.drop_index(batch_op.f("ix_pos_override_tokens_supervisor_user_id"))
        batch_op.drop_index(batch_op.f("ix_pos_override_tokens_cashier_user_id"))
        batch_op.drop_index(batch_op.f("ix_pos_override_tokens_action"))
        batch_op.drop_index(batch_op.f("ix_pos_override_tokens_tenant_id"))
    op.drop_table("pos_override_tokens")

    with op.batch_alter_table("pos_cash_movements", schema=None) as batch_op:
        batch_op.drop_index("idx_pos_cash_movement_shift")
        batch_op.drop_index("idx_pos_cash_movement_session")
        batch_op.drop_index(batch_op.f("ix_pos_cash_movements_movement_type"))
        batch_op.drop_index(batch_op.f("ix_pos_cash_movements_session_id"))
        batch_op.drop_index(batch_op.f("ix_pos_cash_movements_user_id"))
        batch_op.drop_index(batch_op.f("ix_pos_cash_movements_branch_id"))
        batch_op.drop_index(batch_op.f("ix_pos_cash_movements_tenant_id"))
    op.drop_table("pos_cash_movements")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("supervisor_pin_hash")

    with op.batch_alter_table("pos_shifts", schema=None) as batch_op:
        batch_op.drop_column("total_pay_outs")
        batch_op.drop_column("total_pay_ins")
        batch_op.drop_column("total_change_given")

    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.drop_column("total_pay_outs")
        batch_op.drop_column("total_pay_ins")
        batch_op.drop_column("total_change_given")
        batch_op.drop_column("paused_at")
        batch_op.drop_column("terminal_id")
