"""package module entitlements

Adds the module flags that production code already enforces but that had no
Package counterpart. Without these columns no subscription could grant or
withhold maintenance, partners, campaigns, warranty, fixed assets, shipments
or custom integrations; tenants silently inherited model defaults.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "k1m2n3o4p5q6"
down_revision = "t8u9v0w1x2y3"
branch_labels = None
depends_on = None

MODULE_FLAGS = (
    "enable_maintenance",
    "enable_partners",
    "enable_campaigns",
    "enable_warranty_tracking",
    "enable_fixed_assets",
    "enable_shipments",
    "allow_custom_integrations",
)


def upgrade():
    with op.batch_alter_table("packages") as batch:
        for col in MODULE_FLAGS:
            default = col == "enable_shipments"
            batch.add_column(
                sa.Column(
                    col,
                    sa.Boolean(),
                    nullable=True,
                    server_default=sa.text("true" if default else "false"),
                )
            )


def downgrade():
    with op.batch_alter_table("packages") as batch:
        for col in MODULE_FLAGS:
            batch.drop_column(col)
