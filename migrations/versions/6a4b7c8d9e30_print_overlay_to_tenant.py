"""Move the full print/invoice profile onto each tenant (single source of truth).

Before this revision the identity and legal facts lived on ``tenants`` while the
printing form, layout and overlay lived only on the shared ``invoice_settings``
row. That split meant every fact had to be entered twice, the two copies
drifted apart, and — worse — an ``InvoiceSettings`` row seeded lazily with a
``SELECT FOR UPDATE`` on ``document_sequence`` was reachable by print code.

This revision gives ``tenants`` every print/overlay column the templates read,
copies values from that tenant's single active ``invoice_settings`` row (never
from an ambiguous duplicate), carries legacy alternate spellings forward, then
drops the retired alias columns. Prior ``footer_invoice_text_*`` values are
merged into ``footer_text_*`` and the legacy columns are removed. No data is
lost. Rows are never deleted from ``invoice_settings`` — it is the historical
source each backfill reads before being retired.

Ambiguous tenants (more than one active invoice_settings row) are intentionally
skipped, not guessed; those print-only fields remain at tenant defaults until
an operator resolves the conflict.

Revision ID: 6a4b7c8d9e30
Revises: 2f8a0b4c9d31
"""

import sqlalchemy as sa
from alembic import op

revision = "6a4b7c8d9e30"
down_revision = "2f8a0b4c9d31"
branch_labels = None
depends_on = None

# Columns added nullable so old rows behave exactly as before until the
# server/render defaults kick in (or the owner fills them in).
_ADD_COLUMNS = (
    ("logo_path", sa.String(500)),
    ("stamp_url", sa.String(500)),
    ("signature_url", sa.String(500)),
    ("paper_size", sa.String(20)),
    ("orientation", sa.String(20)),
    ("show_logo", sa.Boolean()),
    ("logo_position", sa.String(20)),
    ("logo_size", sa.String(20)),
    ("text_color", sa.String(20)),
    ("terms_conditions_ar", sa.Text()),
    ("terms_conditions_en", sa.Text()),
    ("footer_text_ar", sa.Text()),
    ("footer_text_en", sa.Text()),
    ("default_receipt_note_ar", sa.Text()),
    ("default_receipt_note_en", sa.Text()),
    ("enable_qr_code", sa.Boolean()),
    ("qr_position", sa.String(20)),
    ("enable_watermark", sa.Boolean()),
    ("watermark_text", sa.String(200)),
    ("watermark_image_path", sa.String(500)),
    ("watermark_opacity", sa.Numeric(3, 2)),
    ("show_barcode", sa.Boolean()),
    ("show_page_numbers", sa.Boolean()),
    ("show_due_date", sa.Boolean()),
    ("facebook_url", sa.String(200)),
    ("instagram_url", sa.String(200)),
    ("whatsapp_number", sa.String(50)),
    ("show_terms", sa.Boolean()),
)

# Text values: empty string and NULL both mean "not set"; never overwrite a
# tenant value that already exists.
_TEXT_BACKFILL = {
    "bank_name": "bank_name",
    "bank_account_number": "bank_account_number",
    "iban": "iban",
    "swift_code": "swift_code",
    "invoice_header_color": "header_color",
    "invoice_accent_color": "accent_color",
    "payment_terms_ar": "payment_terms_ar",
    "payment_terms_en": "payment_terms_en",
    "default_invoice_note_ar": "default_invoice_note_ar",
    "default_invoice_note_en": "default_invoice_note_en",
    "default_receipt_note_ar": "default_receipt_note_ar",
    "default_receipt_note_en": "default_receipt_note_en",
    "active_invoice_template": "active_template",
    "logo_path": "logo_path",
    "stamp_url": "stamp_url",
    "signature_url": "signature_url",
    "paper_size": "paper_size",
    "orientation": "orientation",
    "logo_position": "logo_position",
    "logo_size": "logo_size",
    "text_color": "text_color",
    "terms_conditions_ar": "terms_conditions_ar",
    "terms_conditions_en": "terms_conditions_en",
    "footer_text_ar": "footer_text_ar",
    "footer_text_en": "footer_text_en",
    "qr_position": "qr_position",
    "watermark_text": "watermark_text",
    "watermark_image_path": "watermark_image_path",
    "facebook_url": "facebook_url",
    "instagram_url": "instagram_url",
    "whatsapp_number": "whatsapp_number",
}

# Non-text (boolean / numeric): plain COALESCE against the tenant copy.
_SCALAR_BACKFILL = {
    "show_logo": "show_logo",
    "enable_qr_code": "enable_qr_code",
    "enable_watermark": "enable_watermark",
    "show_barcode": "show_barcode",
    "show_page_numbers": "show_page_numbers",
    "show_due_date": "show_due_date",
    "show_terms": "show_terms",
    "watermark_opacity": "watermark_opacity",
    "default_language": "default_language",
}

# Alternate historical names that exist only on the tenants side.
_TENANT_ONLY_ALIAS = {"footer_invoice_text_ar": "footer_text_ar", "footer_invoice_text_en": "footer_text_en"}

_RETIRED = ("footer_invoice_text_ar", "footer_invoice_text_en")


# Optional profile fields may be NULL today; rendering must behave like a
# freshly created tenant. These literal defaults match the model definitions.
_TEXT_DEFAULTS = {
    "paper_size": "'A4'",
    "orientation": "'portrait'",
    "logo_position": "'left'",
    "logo_size": "'medium'",
    "text_color": "'#333333'",
    "qr_position": "'bottom-right'",
    "watermark_image_path": None,
    "watermark_text": None,
    "watermark_opacity": None,
}

_SCALAR_DEFAULTS = {
    "show_logo": "true",
    "enable_qr_code": "true",
    "enable_watermark": "false",
    "show_barcode": "true",
    "show_page_numbers": "true",
    "show_due_date": "true",
    "show_terms": "true",
    "watermark_opacity": "0.10",
}


def _text_assignments(tenant_column, source):
    default = _TEXT_DEFAULTS.get(tenant_column)
    expr = f"COALESCE(NULLIF(tenants.{tenant_column}, ''), source.{tenant_column}"
    if default is not None:
        expr += f", {default}"
    return f"{tenant_column} = {expr})"


def _scalar_assignment(tenant_column):
    default = _SCALAR_DEFAULTS.get(tenant_column)
    expr = f"COALESCE(tenants.{tenant_column}, source.{tenant_column}"
    if default is not None:
        expr += f", {default}"
    return f"{tenant_column} = {expr})"


def _legacy_footer_carry(connection, tenant_columns):
    for old, new in _TENANT_ONLY_ALIAS.items():
        if old in tenant_columns:
            connection.execute(
                sa.text(f"UPDATE tenants SET {new} = COALESCE(NULLIF({new}, ''), {old}) WHERE {old} IS NOT NULL")
            )


def _backfill(connection):
    """Copy from the single active settings row per tenant into empty fields."""
    select_parts = []
    assignments = []
    for tenant_column, source in _TEXT_BACKFILL.items():
        select_parts.append(f"s.{source} AS {tenant_column}")
        assignments.append(_text_assignments(tenant_column, source))
    for tenant_column, source in _SCALAR_BACKFILL.items():
        select_parts.append(f"s.{source} AS {tenant_column}")
        assignments.append(_scalar_assignment(tenant_column))

    assignment_sql = ",\n                ".join(assignments)
    select_columns = ",\n".join(select_parts)
    # Only the single-active-row case is allowed; ambiguous tenant rows are
    # never guessed between. No competing row is ever selected.
    connection.execute(
        sa.text(
            f"""
            UPDATE tenants
            SET {assignment_sql}
            FROM (
                SELECT tenant_id,
                       {select_columns}
                FROM invoice_settings AS s
                WHERE s.is_active = true
                  AND NOT EXISTS (
                    SELECT 1 FROM invoice_settings AS other
                    WHERE other.tenant_id = s.tenant_id
                      AND other.is_active = true
                      AND other.id <> s.id
                )
            ) AS source
            WHERE tenants.id = source.tenant_id
            """
        )
    )


def _add_tenant_columns(connection):
    existing = {column["name"] for column in sa.inspect(connection).get_columns("tenants")}
    with op.batch_alter_table("tenants") as batch_op:
        for name, column_type in _ADD_COLUMNS:
            if name not in existing:
                batch_op.add_column(sa.Column(name, column_type, nullable=True))
    return existing | {name for name, _ in _ADD_COLUMNS}


def upgrade():
    connection = op.get_bind()
    tenant_columns = _add_tenant_columns(connection)

    # Carry forward legacy alternate tenant-column spellings first so the
    # backfill below takes precedence only on genuinely empty fields.
    _legacy_footer_carry(connection, tenant_columns)
    _backfill(connection)

    # Data has been carried forward; drop the retired alias columns so the
    # tenant profile has exactly one place for every fact.
    with op.batch_alter_table("tenants") as batch_op:
        for retired in _RETIRED:
            if retired in tenant_columns:
                batch_op.drop_column(retired)


def downgrade():
    connection = op.get_bind()
    tenant_columns = {column["name"] for column in sa.inspect(connection).get_columns("tenants")}
    # Restore the retired legacy footer columns (f3e4/2f8a expect them).
    with op.batch_alter_table("tenants") as batch_op:
        for retired in _RETIRED:
            if retired not in tenant_columns:
                batch_op.add_column(sa.Column(retired, sa.Text(), nullable=True))
    for retired, live in (("footer_invoice_text_ar", "footer_text_ar"), ("footer_invoice_text_en", "footer_text_en")):
        connection.execute(
            sa.text(f"UPDATE tenants SET {retired} = {live} WHERE {live} IS NOT NULL AND {retired} IS NULL")
        )
    with op.batch_alter_table("tenants") as batch_op:
        for name, _ in reversed(_ADD_COLUMNS):
            batch_op.drop_column(name)
