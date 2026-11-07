"""Resolve the document profile for one tenant.

The Tenant row is the single source of truth for every fact a document shows.
Legacy ``invoice_settings`` rows are never consulted while rendering. This
module builds a transient snapshot object (never attached to the SQLAlchemy
session) so document templates keep a stable attribute namespace. The module
never mutates, seeds or selects rows.
"""

from __future__ import annotations

# tenant attribute -> attribute name exposed to the document templates
_FIELD_MAP = {
    "name_ar": "company_name_ar",
    "name_en": "company_name_en",
    "address_ar": "address_ar",
    "address_en": "address_en",
    "phone_1": "phone_1",
    "phone_2": "phone_2",
    "email": "email",
    "website": "website",
    "tax_number": "tax_number",
    "commercial_register": "commercial_register",
    "license_number": "license_number",
    "logo_url": "logo_url",
    "logo_path": "logo_path",
    "stamp_url": "stamp_url",
    "signature_url": "signature_url",
    "bank_name": "bank_name",
    "bank_account_number": "bank_account_number",
    "iban": "iban",
    "swift_code": "swift_code",
    "invoice_header_color": "header_color",
    "invoice_accent_color": "accent_color",
    "text_color": "text_color",
    "payment_terms_ar": "payment_terms_ar",
    "payment_terms_en": "payment_terms_en",
    "terms_conditions_ar": "terms_conditions_ar",
    "terms_conditions_en": "terms_conditions_en",
    "footer_text_ar": "footer_text_ar",
    "footer_text_en": "footer_text_en",
    "default_invoice_note_ar": "default_invoice_note_ar",
    "default_invoice_note_en": "default_invoice_note_en",
    "default_receipt_note_ar": "default_receipt_note_ar",
    "default_receipt_note_en": "default_receipt_note_en",
    "active_invoice_template": "active_template",
    "paper_size": "paper_size",
    "orientation": "orientation",
    "show_logo": "show_logo",
    "logo_position": "logo_position",
    "logo_size": "logo_size",
    "enable_qr_code": "enable_qr_code",
    "qr_position": "qr_position",
    "enable_watermark": "enable_watermark",
    "watermark_text": "watermark_text",
    "watermark_image_path": "watermark_image_path",
    "watermark_opacity": "watermark_opacity",
    "default_language": "default_language",
    "show_barcode": "show_barcode",
    "show_page_numbers": "show_page_numbers",
    "show_due_date": "show_due_date",
    "show_terms": "show_terms",
    "facebook_url": "facebook_url",
    "instagram_url": "instagram_url",
    "whatsapp_number": "whatsapp_number",
    # Profile facts carried into the snapshot but never written by the form
    "city": "city",
    "country": "country",
    "mobile": "mobile",
    "vat_number": "vat_number",
    "logo_dark_url": "logo_dark_url",
    "favicon_url": "favicon_url",
}
_REVERSED_FIELD_MAP = {snapshot_field: tenant_field for tenant_field, snapshot_field in _FIELD_MAP.items()}

_BOOLEAN_KEYS = {
    "show_logo",
    "show_barcode",
    "show_page_numbers",
    "show_due_date",
    "show_terms",
    "enable_qr_code",
    "enable_watermark",
}


class EffectiveInvoiceSettings:
    """Transient snapshot of one tenant's document profile.

    Attribute namespace matches what the document templates expect. Never
    attached to the SQLAlchemy session; unknown attributes resolve to "" so an
    omitted optional field never breaks rendering.
    """

    _transient = True

    def __init__(self, tenant, overlay):
        overlay = dict(overlay)
        self.tenant_id = tenant.id
        self.is_active = bool(overlay.pop("is_active", True))
        self._tenant = tenant
        self.__dict__.update(overlay)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return ""

    def __bool__(self):
        return True

    @property
    def tenant(self):
        return self._tenant


def build_invoice_settings_snapshot(tenant, source_settings=None) -> EffectiveInvoiceSettings:
    """Construct a detached snapshot of one tenant's document profile."""
    overlay = {
        "company_name_ar": tenant.name_ar or tenant.name or "",
        "company_name_en": tenant.name_en or tenant.name or tenant.name_ar or "",
    }
    for tenant_field, snapshot_field in _FIELD_MAP.items():
        if hasattr(tenant, tenant_field):
            value = getattr(tenant, tenant_field)
            if value is not None:
                overlay[snapshot_field] = value
    if source_settings is not None:
        for name in ("created_at", "updated_at", "updated_by", "id"):
            if hasattr(source_settings, name):
                overlay[name] = getattr(source_settings, name)
        overlay["is_active"] = bool(getattr(source_settings, "is_active", True))
    return EffectiveInvoiceSettings(tenant, overlay)


def apply_snapshot_to_tenant(tenant, form_values, *, allow_files=None):
    """Apply the unified invoice settings form directly to a tenant.

    Form values arrive keyed by the template-facing snapshot names; they are
    written onto the matching tenant columns. Omitted keys are ignored;
    explicitly submitted blank strings clear a field. Booleans come back as
    real booleans.
    """
    for snapshot_field, tenant_field in _REVERSED_FIELD_MAP.items():
        if snapshot_field not in form_values:
            continue
        value = form_values[snapshot_field]
        if snapshot_field in _BOOLEAN_KEYS:
            value = bool(value)
        setattr(tenant, tenant_field, value)
    if "company_name_ar" in form_values or "company_name_en" in form_values:
        name_ar = form_values.get("company_name_ar", tenant.name_ar or "") or ""
        name_en = form_values.get("company_name_en", tenant.name_en or "") or name_ar or ""
        tenant.name = name_en or name_ar or tenant.name
    if allow_files:
        for snapshot_field, filename in allow_files.items():
            tenant_field = _REVERSED_FIELD_MAP.get(snapshot_field)
            if tenant_field and filename:
                setattr(tenant, tenant_field, filename)
    return tenant


def resolve_print_profile(tenant_id):
    """Resolve one tenant's print/profile view without writing anything."""
    if tenant_id is None:
        return None

    from extensions import db
    from models.tenant import Tenant

    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        return None
    return build_invoice_settings_snapshot(tenant)
