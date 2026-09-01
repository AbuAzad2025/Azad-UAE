"""backfill is_contra for 1190, 3300, 5201 and move 2122 to 1100 parent

Revision ID: 1c2195e00e66
Revises: cdefc18af945
Create Date: 2026-09-01

F-08 (audit fix):
- Mark 1190 (Accum.Dep), 3300 (Owner Drawings), 5201 (Inventory Gain) is_contra=true
- Move 2122 (VAT Input) parent from 2120 (liability) to 1100 (Current Assets)
- Move 2122 from level 3 to level 2
- Note: postable group accounts (1130/1140/2110/2120/4100/5100/5150) stay is_header=false
  because the GL engine posts directly to them via concepts; forcing headers would break posting.
- All idempotent via WHERE guards
"""

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "1c2195e00e66"
down_revision = "cdefc18af945"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Mark contra accounts
    op.execute(
        sa.text("UPDATE gl_accounts SET is_contra = true WHERE code IN ('1190','3300','5201') AND is_contra = false")
    )

    # 2. Re-parent 2122 (VAT Input) under 1100 (Current Assets) instead of 2120
    op.execute(
        sa.text(
            """
            UPDATE gl_accounts AS child
            SET parent_id = (SELECT id FROM gl_accounts AS parent
                             WHERE parent.tenant_id = child.tenant_id
                               AND parent.code = '1100' AND parent.is_header = true
                             LIMIT 1),
                level = 2
            WHERE child.code = '2122'
              AND EXISTS (SELECT 1 FROM gl_accounts p
                          WHERE p.tenant_id = child.tenant_id
                            AND p.code = '1100' AND p.is_header = true)
            """
        )
    )


def downgrade():
    with contextlib.suppress(Exception):
        op.execute(sa.text("UPDATE gl_accounts SET is_contra = false WHERE code IN ('1190','3300','5201')"))
    with contextlib.suppress(Exception):
        op.execute(
            sa.text(
                """
                UPDATE gl_accounts AS child
                SET parent_id = (SELECT id FROM gl_accounts AS parent
                                 WHERE parent.tenant_id = child.tenant_id
                                   AND parent.code = '2120' AND parent.is_header = false
                                 LIMIT 1),
                    level = 3
                WHERE child.code = '2122'
                """
            )
        )
