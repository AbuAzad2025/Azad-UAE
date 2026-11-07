"""Mapping between tenant profile fields and the existing print settings."""

# Keep the mapping explicit: several old print columns use different names.
# The invoice settings row is retained while document renderers are migrated.
PROFILE_TO_INVOICE_SETTINGS = {
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
    "bank_name": "bank_name",
    "bank_account_number": "bank_account_number",
    "iban": "iban",
    "swift_code": "swift_code",
    "invoice_header_color": "header_color",
    "invoice_accent_color": "accent_color",
    "payment_terms_ar": "payment_terms_ar",
    "payment_terms_en": "payment_terms_en",
    "footer_invoice_text_ar": "footer_text_ar",
    "footer_invoice_text_en": "footer_text_en",
    "default_invoice_note_ar": "default_invoice_note_ar",
    "default_invoice_note_en": "default_invoice_note_en",
    "active_invoice_template": "active_template",
}


def sync_invoice_profile(tenant, settings, fields, *, skip_empty=False):
    """Copy selected profile fields without touching unrelated settings."""
    for field in fields:
        target = PROFILE_TO_INVOICE_SETTINGS.get(field)
        if target is None:
            continue
        value = getattr(tenant, field, None)
        if skip_empty and not value:
            continue
        if field in ("name_ar", "name_en") and value is None:
            # The legacy print columns are NOT NULL even though name_en on
            # the tenant is optional.
            value = getattr(tenant, "name", None) or ""
        setattr(settings, target, value)
