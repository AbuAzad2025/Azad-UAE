"""tenant ai_external_sharing_enabled privacy flag

Per-tenant AI privacy opt-out (P4-2): when False, prompts sent to external
LLM providers are stripped of granular business data.

Revision ID: a1b2c3d4e5f6
Revises: 004deb545b88
Create Date: 2026-07-31 22:25:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "004deb545b88"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_external_sharing_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade():
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("ai_external_sharing_enabled")
