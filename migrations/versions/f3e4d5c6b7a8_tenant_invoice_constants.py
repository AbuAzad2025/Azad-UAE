"""Move invoice constants into the tenant profile (single source of truth).

Every invoice/receipt reads bank info, payment terms, footer, default
note, header/accent colors and the active template from
``invoice_settings`` today, while ``tenants`` owns the identity (name,
tax number, CR, address). That split is exactly why the same fact must be
entered twice and why the two copies drifted apart. This revision puts
these print-time constants on ``tenants`` as the single source of truth;
``InvoiceSettings`` keeps only its signature/stamp/logo-upload extras and
inherits the rest from the tenant on first use
(``InvoiceSettings._seed_from_tenant``).

All columns are nullable with no default, so existing tenants behave as
before until the owner fills them in.

Revision ID: f3e4d5c6b7a8
Revises: c5d6e7f8a9b0
"""

import sqlalchemy as sa
from alembic import op

revision = "f3e4d5c6b7a8"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("bank_name", sa.String(200)),
    ("bank_account_number", sa.String(100)),
    ("iban", sa.String(100)),
    ("swift_code", sa.String(50)),
    ("invoice_header_color", sa.String(20)),
    ("invoice_accent_color", sa.String(20)),
    ("payment_terms_ar", sa.Text()),
    ("payment_terms_en", sa.Text()),
    ("footer_invoice_text_ar", sa.Text()),
    ("footer_invoice_text_en", sa.Text()),
    ("default_invoice_note_ar", sa.Text()),
    ("default_invoice_note_en", sa.Text()),
    ("active_invoice_template", sa.String(50)),
)


def upgrade():
    for name, column_type in _COLUMNS:
        op.add_column("tenants", sa.Column(name, column_type, nullable=True))


def downgrade():
    for name, _ in reversed(_COLUMNS):
        op.drop_column("tenants", name)
