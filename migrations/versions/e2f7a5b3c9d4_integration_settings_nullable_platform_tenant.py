"""integration_settings tenant_id nullable for platform-global rows.

The owner-panel integrations page manages platform-level services with
tenant_id=None. The column was hardened to NOT NULL without updating
get_service_config, so the first page visit crashed with a
NotNullViolation on auto-create. Platform rows use NULL tenant (same
convention as payment_logs platform audit rows); the platform query path
strictly matches NULL rows so it can never leak a tenant's row.
"""

import sqlalchemy as sa
from alembic import op

revision = "e2f7a5b3c9d4"
down_revision = "d1e6f4a2b8c3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("integration_settings") as batch:
        batch.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Only re-tighten when no platform (NULL-tenant) rows exist.
    bind = op.get_bind()
    nulls = bind.execute(sa.text("SELECT COUNT(*) FROM integration_settings WHERE tenant_id IS NULL")).scalar()
    if nulls:
        raise RuntimeError(f"Cannot downgrade: {nulls} platform integration_settings rows have NULL tenant_id")
    with op.batch_alter_table("integration_settings") as batch:
        batch.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
