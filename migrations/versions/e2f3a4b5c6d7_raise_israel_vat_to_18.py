"""Raise Israel VAT from 17.00 to 18.00.

The Knesset set Israel's standard VAT rate to 18% effective 2025-01-01. Every
IL tenant backfilled by ``a7b8c9d0e1f2`` at 17.00 (the then-declared profile
value) is not compliant; invoices printed from this system would under-collect
tax. Only tenants with ``vat_country='IL'`` whose ``default_tax_rate`` is
exactly 17.00 are raised. A tenant at any other stored rate is untouched —
including a deliberately chosen rate set by an operator after 2025-01-01
(e.g. zero-rated reporting is denied by the country-lock invariant anyway).

Revision ID: e2f3a4b5c6d7
Revises: 6a4b7c8d9e30
"""

from alembic import op
from sqlalchemy import text

revision = "e2f3a4b5c6d7"
down_revision = "6a4b7c8d9e30"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        text(
            "UPDATE tenants SET default_tax_rate = :rate WHERE default_tax_rate = :old AND vat_country = :code"
        ).bindparams(rate="18.00", old="17.00", code="IL")
    )


def downgrade():
    # Deliberately no-op: 18% is the statutory rate in force since 2025-01-01;
    # lowering it again would restate overridden law. Rows upgraded here were
    # corrected in place, not merged with distinct sources.
    pass
