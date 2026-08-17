"""add employee bank/wps fields for WPS SIF export

Batch 1.2 — Add bank_code, bank_name, iban columns to the employees
table to support WPS (Wage Protection System) SIF file generation
for both UAE and Palestine jurisdictions.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 17:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("bank_code", sa.String(20), nullable=True))
    op.add_column("employees", sa.Column("bank_name", sa.String(100), nullable=True))
    op.add_column("employees", sa.Column("iban", sa.String(50), nullable=True))


def downgrade():
    op.drop_column("employees", "iban")
    op.drop_column("employees", "bank_name")
    op.drop_column("employees", "bank_code")
