VALID_BUSINESS_TYPES = frozenset(
    [
        "general",
        "automotive",
        "electronics",
        "supermarket",
        "pharmacy",
        "restaurant",
        "construction",
        "textile",
        "jewelry",
        "retail",
        "trading",
        "batteries",
        "mobile_new",
        "mobile_used",
        "mobile_parts",
        "clothing",
        "multi_branch_retail",
    ]
)

BUSINESS_TYPE_LABELS = {
    "general": ("عام", "General"),
    "automotive": ("كراج / قطع غيار سيارات", "Automotive"),
    "electronics": ("إلكترونيات", "Electronics"),
    "supermarket": ("سوبرماركت", "Supermarket"),
    "pharmacy": ("صيدلية", "Pharmacy"),
    "restaurant": ("مطعم / كافيه", "Restaurant"),
    "construction": ("مقاولات", "Construction"),
    "textile": ("أقمشة / ملابس", "Textile"),
    "jewelry": ("مجوهرات / ذهب", "Jewelry"),
    "retail": ("تجارة Retail", "Retail"),
    "trading": ("تجارة عامة", "Trading"),
    "batteries": ("بطاريات", "Batteries"),
    "mobile_new": ("موبايلات جديدة", "New Mobile Phones"),
    "mobile_used": ("موبايلات مستعملة", "Used Mobile Phones"),
    "mobile_parts": ("قطع غيار موبايلات", "Mobile Spare Parts"),
    "clothing": ("ملابس", "Clothing"),
    "multi_branch_retail": ("تجارة متعددة الفروع", "Multi-Branch Retail"),
}


class IndustryService:
    @staticmethod
    def get_fields_for(industry_code, applies_to="product"):
        from models.industry_field_definition import IndustryFieldDefinition

        return (
            IndustryFieldDefinition.query.filter_by(
                industry_code=industry_code,
                applies_to=applies_to,
                is_active=True,
            )
            .order_by(IndustryFieldDefinition.sort_order)
            .all()
        )

    @staticmethod
    def get_core_fields():
        return IndustryService.get_fields_for("core", "product")

    @staticmethod
    def get_business_type_choices():
        return [(code, f"{ar} / {en}") for code, (ar, en) in BUSINESS_TYPE_LABELS.items()]

    @staticmethod
    def validate_industry_code(code):
        return code in VALID_BUSINESS_TYPES

    @staticmethod
    def get_product_effective_industry(product, tenant):
        return getattr(product, "industry", None) or getattr(tenant, "business_type", "general")

    @staticmethod
    def get_all_field_names_for(industry_code):
        fields = IndustryService.get_fields_for(industry_code, "product")
        return [f.field_code for f in fields]

    @staticmethod
    def save_extra_fields(entity, form_data, industry_code):
        fields = IndustryService.get_fields_for(industry_code, "product")
        extra = {}
        for field in fields:
            val = form_data.get(field.field_code)
            if val is not None and str(val).strip() != "":
                extra[field.field_code] = val
        entity.extra_fields = extra


# Business types treated as dine-in / table-service by default.
RESTAURANT_LIKE = frozenset({"restaurant", "cafe"})


def resolve_tenant_industry(tenant) -> dict:
    """Compatibility layer: never return NULL for runtime consumers.

    Falls back to 'general' for business_type and 'retail' for industry so any
    code path (POS profile, GL extension, product fields) is always safe.
    """
    bt = (getattr(tenant, "business_type", None) or "").strip() or "general"
    ind = (getattr(tenant, "industry", None) or "").strip() or "retail"
    return {
        "business_type": bt,
        "industry": ind,
        "is_known": bt in VALID_BUSINESS_TYPES,
    }


def get_pos_profile(tenant):
    """Derive runtime POS feature flags from the tenant's business_type.

    Pure function, no side effects — used to morph the POS UI/API per trade.
    Applies the legacy-NULL fallback so runtime resolution is always safe.
    """
    bt = resolve_tenant_industry(tenant)["business_type"]
    table_enabled = bt in RESTAURANT_LIKE
    return {
        "business_type": bt,
        "mode": "restaurant" if table_enabled else "retail",
        "enable_tables": table_enabled,
        "enable_hold": True,
        "enable_kds": True,
    }
