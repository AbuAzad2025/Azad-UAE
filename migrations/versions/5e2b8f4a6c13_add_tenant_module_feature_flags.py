"""tenant module feature flags - the switches dynamic GL provisioning reads

``services/gl_provisioning_service.py`` provisions a tenant's GL concept
mappings per module, and every non-core module is gated on a tenant feature
flag::

    for mod in GL_MODULE_DEFINITIONS.values():
        if not mod.required:
            flag = mod.feature_flag
            if flag and not getattr(tenant, flag, False):
                continue

The flag is read off the tenant with ``getattr(..., False)``. A flag that has
no column on the ``tenants`` table is therefore always False, so the module is
never provisioned - and under the production default
(``ENABLE_DYNAMIC_GL_MAPPING=True``) the concepts that module owns have no
mapping row, and the posting that needs one is refused outright.

Eight of those flags had no column at all. This revision gives them one:

    enable_shipments            BOOLEAN NOT NULL DEFAULT 1
    enable_campaigns            BOOLEAN NOT NULL DEFAULT 1
    enable_partners             BOOLEAN NOT NULL DEFAULT 1
    enable_fixed_assets         BOOLEAN NOT NULL DEFAULT 1
    enable_donations            BOOLEAN NOT NULL DEFAULT 1
    enable_warranty_tracking    BOOLEAN NOT NULL DEFAULT 1
    enable_bank_reconciliation  BOOLEAN NOT NULL DEFAULT 1
    enable_azad_platform        BOOLEAN NOT NULL DEFAULT 1

``DEFAULT 1`` (true) is the deliberate value. The postings these modules make
- a shipment's revenue, a campaign discount, a partner commission, a
depreciation, a donation, a platform fee - happen on ordinary operations, so
a tenant that has not switched a module off must never have its posting
refused. The flag is the tenant's switch to turn a module off knowingly, not a
gate that silently breaks a normal operation.

The default is kept (not dropped afterwards) so a row inserted outside the ORM
lands on the same value as one inserted through it, and so the model and the
schema agree.

Both statements are idempotent - a column is added only when it is absent -
and the downgrade drops exactly the eight columns this revision creates.

Revision ID: 5e2b8f4a6c13
Revises: b7e1c4a9d305
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "5e2b8f4a6c13"
down_revision = "b7e1c4a9d305"
branch_labels = None
depends_on = None

TABLE = "tenants"

# (column name, server default) - the single declaration both upgrade() and
# downgrade() work from, so the two can never disagree about the column set.
#
# The default is the *string* "1", not sa.text("1"). Alembic renders a plain
# string as a quoted literal ('1'), which PostgreSQL casts to boolean true;
# sa.text("1") renders the integer 1, and PostgreSQL refuses that outright
# ("column is of type boolean but default expression is of type integer").
# The same string is what models/tenant.py declares, so the model and the
# schema carry the same default.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("enable_shipments", "1"),
    ("enable_campaigns", "1"),
    ("enable_partners", "1"),
    ("enable_fixed_assets", "1"),
    ("enable_donations", "1"),
    ("enable_warranty_tracking", "1"),
    ("enable_bank_reconciliation", "1"),
    ("enable_azad_platform", "1"),
)


def _existing_columns() -> set[str]:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return {c["name"] for c in insp.get_columns(TABLE)}
    except Exception:
        return set()


def upgrade() -> None:
    existing = _existing_columns()
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, default in COLUMNS:
            if name in existing:
                continue
            batch_op.add_column(
                sa.Column(
                    name,
                    sa.Boolean(),
                    nullable=False,
                    server_default=default,
                )
            )


def downgrade() -> None:
    existing = _existing_columns()
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, _default in reversed(COLUMNS):
            if name not in existing:
                continue
            batch_op.drop_column(name)
