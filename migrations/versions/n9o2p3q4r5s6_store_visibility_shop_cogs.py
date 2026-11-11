"""store visibility + shop COGS concept

Adds:
- products.is_visible_on_store (boolean, default true) so the tenant can
  control which products appear on the storefront
- SHOP_COGS to the gl_account_mappings concept check constraint so store
  orders can post cost of goods sold to a shop-specific COGS account
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "n9o2p3q4r5s6"
down_revision = "m3a4b5c6d7e8"
branch_labels = None
depends_on = None

#: Concepts that were widened by the maintenance module (revision m3a4b5c6d7e8)
#: and must be preserved when rebuilding the check constraint.
_MAINTENANCE_CONCEPTS = frozenset(
    {
        "MAINTENANCE_REVENUE",
        "MAINTENANCE_AR",
        "MAINTENANCE_AP",
        "MAINTENANCE_COGS",
        "MAINTENANCE_CASH_DIFFERENCE",
        "MAINTENANCE_DEPOSIT",
    }
)


def _rebuild_concept_check() -> None:
    from models._constants import GL_CONCEPT_CODES

    codes = [code for code in GL_CONCEPT_CODES if code not in _MAINTENANCE_CONCEPTS]
    codes.extend(sorted(_MAINTENANCE_CONCEPTS))
    expression = "concept_code IN ({})".format(", ".join(f"'{code}'" for code in codes))
    with op.batch_alter_table("gl_account_mappings") as batch_op:
        batch_op.drop_constraint("ck_gl_account_mappings_concept_code", type_="check")
        batch_op.create_check_constraint("ck_gl_account_mappings_concept_code", expression)


def upgrade():
    # products.is_visible_on_store
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_visible_on_store",
                sa.Boolean(),
                nullable=False,
                server_default="1",
                index=True,
            )
        )

    # Widen gl_account_mappings concept check to include SHOP_COGS
    _rebuild_concept_check()


def downgrade():
    # Remove is_visible_on_store
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("is_visible_on_store")

    # Rebuild concept check without SHOP_COGS
    _rebuild_concept_check()
