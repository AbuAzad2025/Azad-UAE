"""Copy unambiguous existing invoice settings into empty tenant fields.

The preceding revision added nullable fields without transferring existing
settings. Only tenants with exactly one active invoice-settings row are
eligible. Existing profile values and the source settings remain untouched.

Revision ID: 2f8a0b4c9d31
Revises: f3e4d5c6b7a8
"""

from alembic import op
from sqlalchemy import text

revision = "2f8a0b4c9d31"
down_revision = "f3e4d5c6b7a8"
branch_labels = None
depends_on = None

_FIELDS = (
    ("bank_name", "bank_name"),
    ("bank_account_number", "bank_account_number"),
    ("iban", "iban"),
    ("swift_code", "swift_code"),
    ("invoice_header_color", "header_color"),
    ("invoice_accent_color", "accent_color"),
    ("payment_terms_ar", "payment_terms_ar"),
    ("payment_terms_en", "payment_terms_en"),
    ("footer_invoice_text_ar", "footer_text_ar"),
    ("footer_invoice_text_en", "footer_text_en"),
    ("default_invoice_note_ar", "default_invoice_note_ar"),
    ("default_invoice_note_en", "default_invoice_note_en"),
    ("active_invoice_template", "active_template"),
)


def upgrade():
    connection = op.get_bind()
    for target, source in _FIELDS:
        # The only interpolated identifiers are the frozen literals above.
        statement = text(
            f"UPDATE tenants SET {target} = "
            f"(SELECT s.{source} FROM invoice_settings s "
            "WHERE s.tenant_id = tenants.id AND s.is_active = :active) "
            f"WHERE ({target} IS NULL OR trim({target}) = '') "
            "AND (SELECT count(*) FROM invoice_settings s "
            "WHERE s.tenant_id = tenants.id AND s.is_active = :active) = 1 "
            "AND EXISTS (SELECT 1 FROM invoice_settings s "
            "WHERE s.tenant_id = tenants.id AND s.is_active = :active "
            f"AND s.{source} IS NOT NULL AND trim(s.{source}) <> '')"
        )
        connection.execute(statement, {"active": True})


def downgrade():
    # Copied and subsequently edited values cannot be distinguished safely.
    # Keep them; the preceding migration owns the columns and their removal.
    pass
