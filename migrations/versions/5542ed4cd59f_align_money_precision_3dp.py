"""align money precision 2dp vs 3dp

Revision ID: 5542ed4cd59f
Revises: 1c2195e00e66
Create Date: 2026-09-01

LAYER-1 fix D-L1-01: standardize money columns to Numeric(15,3) so they align
with GLJournalLine (15,3). Rows storing cash amounts (donations, card
payments, payment-vault wallets) previously used (15,2)/(10,2), risking
rounding drift when materialized into GL at 3dp. Existing 2-decimal values
widen losslessly to 3 decimals.
"""

import sqlalchemy as sa
from alembic import op

revision = "5542ed4cd59f"
down_revision = "1c2195e00e66"
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
    if _column_exists("card_payments", "amount"):
        with op.batch_alter_table("card_payments", schema=None) as batch_op:
            batch_op.alter_column(
                "amount", existing_type=sa.Numeric(15, 2), type_=sa.Numeric(15, 3), existing_nullable=False
            )

    if _column_exists("donations", "amount_usd"):
        with op.batch_alter_table("donations", schema=None) as batch_op:
            batch_op.alter_column(
                "amount_usd", existing_type=sa.Numeric(15, 2), type_=sa.Numeric(15, 3), existing_nullable=False
            )

    if _column_exists("payment_vault", "daily_limit"):
        with op.batch_alter_table("payment_vault", schema=None) as batch_op:
            batch_op.alter_column(
                "min_donation_amount", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(15, 3), existing_nullable=True
            )
            batch_op.alter_column(
                "max_donation_amount", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(15, 3), existing_nullable=True
            )
            batch_op.alter_column(
                "daily_limit", existing_type=sa.Numeric(15, 2), type_=sa.Numeric(15, 3), existing_nullable=True
            )

    for tbl, col in (("payment_transactions", "amount"), ("payment_logs", "amount")):
        if _column_exists(tbl, col):
            with op.batch_alter_table(tbl, schema=None) as batch_op:
                batch_op.alter_column(
                    col, existing_type=sa.Numeric(15, 2), type_=sa.Numeric(15, 3), existing_nullable=True
                )


def downgrade():
    if _column_exists("card_payments", "amount"):
        with op.batch_alter_table("card_payments", schema=None) as batch_op:
            batch_op.alter_column(
                "amount", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(15, 2), existing_nullable=False
            )

    if _column_exists("donations", "amount_usd"):
        with op.batch_alter_table("donations", schema=None) as batch_op:
            batch_op.alter_column(
                "amount_usd", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(15, 2), existing_nullable=False
            )

    if _column_exists("payment_vault", "daily_limit"):
        with op.batch_alter_table("payment_vault", schema=None) as batch_op:
            batch_op.alter_column(
                "min_donation_amount", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(10, 2), existing_nullable=True
            )
            batch_op.alter_column(
                "max_donation_amount", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(10, 2), existing_nullable=True
            )
            batch_op.alter_column(
                "daily_limit", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(15, 2), existing_nullable=True
            )

    for tbl, col in (("payment_transactions", "amount"), ("payment_logs", "amount")):
        if _column_exists(tbl, col):
            with op.batch_alter_table(tbl, schema=None) as batch_op:
                batch_op.alter_column(
                    col, existing_type=sa.Numeric(15, 3), type_=sa.Numeric(15, 2), existing_nullable=True
                )
