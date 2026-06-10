Subject: Industry-Adaptive Product & Warehouse Fields — Major Feature Required

Dr. AI,

I have completed a deep manual audit of the industry-adaptive field system for Azad ERP. The full technical report is in:

  docs/industry-adaptive-audit-report.md

The core problem: Tenant.business_type and Tenant.industry exist but are completely unused for schema customization. All tenants see the same Product and Warehouse fields regardless of industry.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE A — Foundation: Industry Field Definition System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A1  CREATE models/industry_field_definition.py
    Master registry of per-industry fields.
    Columns:
      id, industry_code (en), field_code (en),
      field_name_ar, field_name_en, field_type (text/number/date/select/boolean),
      field_options (JSON for select), applies_to (product/warehouse/both),
      sort_order, is_required, is_active

A2  CREATE seed script: scripts/seed_industry_fields.py
    Pre-populate definitions for these industries:
      automotive    — car_make, car_model, year, engine_cc, transmission, fuel_type
      electronics   — device_type, storage_gb, color, imei_required, screen_size
      supermarket   — expiry_date, weight_kg, organic, halal_certified, batch_number
      pharmacy      — expiry_date, batch_number, prescription_required, storage_temp
      restaurant    — expiry_date, weight_kg, allergen_info, halal_certified
      construction  — material_type, unit_type, grade, supplier_cert
      textile       — fabric_type, color, size_chart, origin_country
      jewelry       — metal_type, purity_karat, weight_gram, gem_type
      retail        — color, size, material, season, country_of_origin
      general       — (no extra fields beyond defaults)

A3  ALTER models/tenant.py
    business_type = db.Column(db.String(50), default='general', nullable=False)
    Add validation: must be one of the 10 defined industry codes.
    Add index on business_type.

A4  ALTER models/product.py
    Add: extra_fields = db.Column(db.JSON, default=dict)
    For SQLite compatibility fallback: db.Text with JSON serialization.
    Keep all existing columns — extra_fields is additive only.

A5  ALTER models/warehouse.py
    Add: extra_fields = db.Column(db.JSON, default=dict)
    Same approach as Product.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE B — UI: Dynamic Forms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

B1  MODIFY templates/owner/tenant_create.html
    Replace business_type <input> with <select>:
      <select name="business_type" required>
        <option value="">-- اختر نوع النشاط --</option>
        {% for code, name_ar, name_en in business_types %}
        <option value="{{ code }}">{{ name_ar }} / {{ name_en }}</option>
        {% endfor %}
      </select>
    Same for tenant_edit.html.

B2  CREATE templates/partials/industry_fields.html
    Reusable partial that receives:
      - industry_code
      - applies_to ('product' or 'warehouse')
      - existing_values (dict)
    Renders input fields dynamically based on IndustryFieldDefinition query.
    Supports: text, number, date, select, boolean.
    Labels in Arabic (current_language == 'ar') or English.

B3  MODIFY templates/products/create.html
    Include industry_fields partial after standard fields.
    Pass: tenant.business_type, 'product', {}

B4  MODIFY templates/products/edit.html
    Include industry_fields partial.
    Pass: tenant.business_type, 'product', product.extra_fields

B5  MODIFY templates/warehouse/create.html and edit.html
    Include industry_fields partial for warehouse.

B6  MODIFY routes/owner.py
    In tenant_create and tenant_edit:
      Pass business_types = IndustryService.get_business_type_choices()
    In POST handler: validate business_type against allowed list.

B7  MODIFY routes/products.py
    In create() and edit() POST handlers:
      After saving product, call:
        IndustryService.save_extra_fields(product, request.form, current_user.tenant)
    In GET handlers:
      Pass industry_fields = IndustryService.get_fields_for(tenant, 'product')

B8  MODIFY routes/warehouse.py
    Same pattern as products — save/load extra_fields for warehouses.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE C — Services & Logic
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

C1  CREATE services/industry_service.py
    Methods:
      get_fields_for(tenant, applies_to='product') -> list[IndustryFieldDefinition]
      save_extra_fields(entity, form_data, tenant) -> None
      get_extra_field(entity, field_code) -> Any
      get_business_type_choices() -> list[tuple[code, name_ar, name_en]]
      validate_industry_code(code) -> bool

C2  MODIFY services/product_service.py
    Add get_product_display_fields(product) -> dict:
      Merges standard fields + extra_fields for API/JSON response.
      Filters extra_fields to only include fields defined for product's tenant industry.

C3  MODIFY services/stock_service.py
    In create_movement and related methods:
      If product has extra_fields with batch_number or expiry_date:
        Include in StockMovement.notes or add new StockMovement.extra_fields.
    (Optional — depends on whether stock movements need industry context.)

C4  MODIFY services/shop_service.py (storefront)
    Product display for online store:
      Show relevant extra fields based on tenant industry.
      E.g., for electronics: show color, storage_gb in product card.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE D — Search & Filter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

D1  MODIFY warehouse/index.html product search
    Add filters for industry-specific fields:
      - Automotive: filter by car_make + car_model
      - Electronics: filter by device_type + storage_gb
      - Supermarket: filter by expiry_date range
    These filters only appear when tenant matches the industry.

D2  MODIFY products/index.html search
    Add advanced search panel with extra field filters.
    Use JSON extraction for filtering (Postgres) or in-memory for SQLite.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE E — Reports & Analytics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

E1  MODIFY reports to include extra fields
    Stock report: include batch_number, expiry_date where relevant.
    Sales report: include car_make, device_type where relevant.

E2  MODIFY AI expertise system
    In ai_training/seed scripts:
      Ensure each tenant's expertise JSON is linked to its business_type.
      Validate that all defined industries have corresponding expertise data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NO REMOVAL of existing columns — extra_fields is purely additive.
2. NO BREAKING CHANGES to existing product/warehouse API.
3. INDUSTRY_CODE must be English (stable identifier) — display names in AR/EN.
4. business_type must be validated against known list — reject unknown values.
5. All changes must include tests.
6. No inline CSS/JS in any modified template — use existing CSS/JS files.
7. SQLite compatibility: use Text with JSON serialization if JSONB not available.
8. Default industry = 'general' — no extra fields shown.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INDUSTRY CODES (English — Stable Identifiers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

general      — عام / General
automotive   — كراج / قطع غيار سيارات / Automotive / Garage
electronics  — إلكترونيات / موبايلات / Electronics / Mobile
supermarket  — سوبرماركت / Supermarket
pharmacy     — صيدلية / Pharmacy
restaurant   — مطعم / كافيه / Restaurant / Cafe
construction — مقاولات / مواد بناء / Construction
textile      — أقمشة / ملابس / Textile / Clothing
jewelry      — مجوهرات / ذهب / Jewelry / Gold
retail       — تجارة Retail / Retail
trading      — تجارة عامة / General Trading

Each code maps to Arabic and English display names.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with tests (unit + integration)
2. Migration scripts for:
   - Adding extra_fields columns
   - Creating industry_field_definition table
   - Seeding default field definitions
3. Updated tenant create/edit forms with industry dropdown
4. Updated product/warehouse forms with dynamic fields
5. Updated docs/industry-adaptive-audit-report.md with completion status
6. No inline CSS/JS in any touched template
7. Report any issues discovered during implementation

Execute Phase A first. Do not start Phase B until Phase A tests pass.
Report completion status per phase.

Proceed.
