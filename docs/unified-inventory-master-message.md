Subject: Unified Inventory, Products, Warehouses & Industry-Adaptive Fields — Master Implementation Plan

Dr. AI,

I have completed the deepest manual audit of Azad ERP's inventory, product, warehouse, pricing, currency, and industry-adaptive systems. The full unified report is in:

  docs/unified-inventory-master-report.md

22 critical issues found across 7 domains (stock, pricing, currency, promotions, industry-adaptive, warranty, shipping, serial/IMEI tracking, product images). This message supersedes all previous inventory and industry-adaptive messages. Execute this plan only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — Foundation: Fix Stock Architecture
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P1.1 CREATE models/warehouse.py additions
    New table: product_warehouse_stock
    Columns: id, tenant_id, product_id, warehouse_id, quantity, updated_at
    Unique: (tenant_id, product_id, warehouse_id)
    FK: product_id → products.id (CASCADE), warehouse_id → warehouses.id (CASCADE)

P1.2 ALTER models/product.py
    Add: extra_fields = db.Column(db.JSON, default=dict)
    Add: price_tiers relationship (to new ProductPriceTier table)
    Keep ALL existing columns — no removal.
    Convert current_stock to @property:
      @property
      def current_stock(self):
          return sum(pws.quantity for pws in self.warehouse_stocks)

P1.3 ALTER models/warehouse.py
    Add: extra_fields = db.Column(db.JSON, default=dict)
    Relationship: warehouse_stocks (to ProductWarehouseStock)

P1.4 REWRITE services/stock_service.py create_movement
    Current: product.current_stock += quantity
    New: update ProductWarehouseStock for specific warehouse
    Fix: default warehouse creation MUST include tenant_id in constructor
    Add: StockService.reconcile_stock(tenant_id) — compare PWS vs sum(StockMovement)

P1.5 FIX GL accounts in stock_service.py
    Replace hardcoded '5150'/'1140' with:
      GLService.resolve_account_by_concept('INVENTORY_ADJUSTMENT_LOSS')
      GLService.resolve_account_by_concept('INVENTORY_ASSET')

P1.6 ADD CLI command
    flask reconcile-stock [--tenant-id=N] [--commit]
    File: cli_commands.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — Pricing Tiers: Wholesale, Retail, Distributor, Rep
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P2.1 CREATE models/product_price_tier.py
    class ProductPriceTier:
        id, tenant_id, product_id, tier_code ('wholesale', 'retail', 'distributor', 'rep'),
        min_quantity, price, currency, is_active
    Unique: (tenant_id, product_id, tier_code)

P2.2 ALTER models/sale.py
    Add: sales_rep_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    Relationship: sales_rep = db.relationship('User', foreign_keys=[sales_rep_id])

P2.3 CREATE models/sales_rep_commission.py
    class SalesRepCommission:
        id, tenant_id, sale_id, sale_line_id (optional),
        sales_rep_id, product_id (optional),
        commission_rate (pct), commission_amount, currency,
        is_paid, paid_at

P2.4 CREATE services/pricing_service.py
    get_price(product, customer_type, qty=1) -> Decimal
    get_price_for_sale_line(product, qty, customer, sales_rep=None) -> dict:
      {unit_price, tier_code, discount_applied, commission_rate}

P2.5 MODIFY routes/products.py
    In create/edit forms: show price tiers (wholesale, retail, distributor)
    In product view: show all tiers

P2.6 MODIFY routes/sales.py
    In create/edit: apply tier pricing based on qty + customer type
    Track sales_rep on Sale
    Auto-create SalesRepCommission entries

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 3 — Campaigns & Promotions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P3.1 CREATE models/campaign.py
    class Campaign:
        id, tenant_id, name, name_ar,
        campaign_type ('percentage', 'fixed', 'bundle', 'flash', 'bogo'),
        discount_value, max_discount_amount,
        start_date, end_date,
        min_order_amount, min_quantity,
        applicable_products JSON (list of product_ids or 'all'),
        applicable_categories JSON,
        is_active, usage_limit, usage_count,
        coupon_code (optional)

P3.2 CREATE models/sale_campaign.py
    Junction: sale_id, campaign_id, discount_amount

P3.3 CREATE services/campaign_service.py
    get_active_campaigns(tenant_id, product_ids=None, category_ids=None) -> list
    apply_campaigns(sale, campaigns) -> discount_amount
    validate_coupon(coupon_code, tenant_id) -> Campaign or None

P3.4 MODIFY routes/sales.py
    In calculate_totals: call CampaignService.apply_campaigns before tax
    Accept coupon_code in form
    Show active campaigns in POS and sales create

P3.5 ADD to storefront (shop)
    Display campaign badges on products
    Apply coupon code at checkout
    Show "Buy X Get Y" bundles

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 4 — Currency Fix (ILS / شيقل)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P4.1 ALTER models/purchase.py
    Add: amount = db.Column(db.Numeric(15,3)) — original currency amount
    Rename: amount_aed → amount_base (keep alias for backward compat)
    Ensure: currency field is used and validated (AED, ILS, USD, etc.)

P4.2 ALTER models/sale.py
    Same pattern: amount + amount_base
    paid_amount + paid_amount_base

P4.3 ALTER models/partner_commission.py
    Add: currency = db.Column(db.String(3))
    Rename: base_amount_aed → base_amount (keep alias)
    Rename: commission_amount_aed → commission_amount (keep alias)

P4.4 MODIFY utils/currency_converter.py (if exists) or CREATE
    convert(amount, from_currency, to_currency, date=None) -> Decimal
    Uses cached rates or fallback to 1:1

P4.5 UPDATE templates/owner/tenant_create.html
    Ensure ILS is in currency dropdown (already exists — verify all forms)
    Check: all currency dropdowns must include AED, ILS, USD at minimum

P4.6 SEARCH & REPLACE all hardcoded '_aed' references
    In models: rename columns with backward-compatible aliases
    In services: use amount_base instead of amount_aed
    In templates: display currency symbol based on tenant currency

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 5 — Industry-Adaptive Dynamic Fields (Hybrid Core + Dynamic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARCHITECTURE: Two-tier field system

  Tier 1 — CORE FIELDS (all products, all industries):
    name, name_ar, sku, barcode, cost_price, regular_price,
    current_stock, min_stock_alert, category_id, unit,
    is_active, has_serial_number, warranty_days

  Tier 2 — INDUSTRY FIELDS (dynamic, per product.industry):
    Stored in product.extra_fields JSONB
    Defined in IndustryFieldDefinition registry
    Product can override tenant's default industry

P5.1 CREATE models/industry_field_definition.py
    class IndustryFieldDefinition:
        id, industry_code (en), field_code (en),
        field_name_ar, field_name_en,
        field_type ('text', 'number', 'date', 'select', 'boolean', 'json'),
        field_options (JSON for select values),
        applies_to ('product', 'warehouse', 'both'),
        sort_order, is_required, is_active

P5.2 ALTER models/tenant.py
    business_type = db.Column(db.String(50), default='general', nullable=False)
    Add validation: must be one of:
      general, automotive, electronics, supermarket, pharmacy,
      restaurant, construction, textile, jewelry, retail, trading,
      batteries, mobile_new, mobile_used, mobile_parts, clothing

P5.3 ALTER models/product.py
    Add: industry = db.Column(db.String(50), nullable=False)
    # defaults to tenant.business_type on create
    # but can be overridden per product
    Add: extra_fields = db.Column(db.JSON, default=dict)

P5.4 CREATE services/industry_service.py
    get_fields_for(industry_code, applies_to='product') -> list
    # Returns IndustryFieldDefinition rows for given industry_code
    # NOT tenant.business_type — allows per-product override

    save_extra_fields(entity, form_data, industry_code) -> None
    # Saves only fields defined for that industry_code

    get_product_effective_industry(product, tenant) -> str
    # Returns product.industry if set, else tenant.business_type

    get_core_fields() -> list
    # Returns the 13 core field definitions (static, always shown)

    get_business_type_choices() -> list of tuples
    validate_industry_code(code) -> bool
    get_all_field_names_for(industry_code) -> list

P5.5 CREATE scripts/seed_industry_fields.py
    Seed CORE field definitions (applies_to='product', industry_code='core'):
      name, name_ar, sku, barcode, cost_price, regular_price,
      current_stock, min_stock_alert, category_id, unit,
      is_active, has_serial_number, warranty_days

    Seed INDUSTRY field definitions:
      batteries: battery_type, voltage, capacity_ah, cold_cranking_amps, dimensions, terminal_type, application
      mobile_new: imei_required, storage_gb, color, model_year, condition, warranty_period
      mobile_used: condition, grade, battery_health_pct, original_box, charger_included, scratches_level
      mobile_parts: compatible_models, part_type, oem_or_aftermarket
      clothing: size, color, fabric_type, season, style_code, brand, care_instructions
      automotive: car_make, car_model, year, engine_cc, transmission, fuel_type
      supermarket: expiry_date, weight_kg, organic, halal_certified, batch_number
      electronics: device_type, storage_gb, color, screen_size, battery_mah
      pharmacy: expiry_date, batch_number, prescription_required, storage_temp
      construction: material_type, unit_type, grade, supplier_cert
      textile: fabric_type, color, size_chart, origin_country
      jewelry: metal_type, purity_karat, weight_gram, gem_type

P5.6 MODIFY templates/owner/tenant_create.html + tenant_edit.html
    Replace <input business_type> with <select required>
    Options from IndustryService.get_business_type_choices()

P5.7 CREATE templates/partials/industry_fields.html
    Reusable partial: receives industry_code, applies_to, existing_values
    Renders inputs dynamically based on IndustryFieldDefinition
    Core fields always shown first, then industry fields

P5.8 MODIFY templates/products/create.html + edit.html
    Always show: Core fields (name, sku, barcode, cost_price, ...)
    Then show: Industry dropdown (default = tenant.business_type)
      <select name="industry">
        <option value="{{ tenant.business_type }}" selected>
          {{ tenant.business_type_display }}
        </option>
        {% for code, name in all_industries %}
        <option value="{{ code }}">{{ name }}</option>
        {% endfor %}
      </select>
    Then include: industry_fields partial with selected industry
    Pass: product.industry or tenant.business_type, 'product', product.extra_fields

P5.9 MODIFY routes/products.py
    In create():
      product.industry = request.form.get('industry', tenant.business_type)
      IndustryService.save_extra_fields(product, request.form, product.industry)
    In edit():
      product.industry = request.form.get('industry', product.industry)
      IndustryService.save_extra_fields(product, request.form, product.industry)
    In GET handlers:
      effective_industry = product.industry if product else tenant.business_type
      core_fields = IndustryService.get_core_fields()
      industry_fields = IndustryService.get_fields_for(effective_industry, 'product')

P5.10 MODIFY templates/warehouse/create.html + edit.html
    Include industry_fields partial for warehouse-specific fields
    Warehouses inherit tenant.business_type (no per-warehouse override needed)

P5.11 ADD JavaScript for dynamic field switching
    When user changes industry dropdown on product form:
      Fetch fields via AJAX: GET /api/industry-fields?code=INDUSTRY
      Replace industry fields section dynamically
    File: static/js/products/industry-fields.js

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 6 — Warranty Tracking
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P6.1 CREATE models/warranty_claim.py
    class WarrantyClaim:
        id, tenant_id, sale_id, sale_line_id, product_id,
        claim_date, claim_type ('repair', 'replacement', 'refund'),
        description, status ('open', 'approved', 'rejected', 'resolved'),
        resolved_at, resolution_notes, cost_to_company

P6.2 ALTER models/sale_line.py (if exists) or check
    If SaleLine exists: add warranty_start_date, warranty_end_date
    If not: add to SaleLine or create SaleLine model

P6.3 CREATE services/warranty_service.py
    create_claim(sale_line, claim_type, description) -> WarrantyClaim
    get_active_warranties(tenant_id) -> list
    get_expiring_warranties(days=30) -> list

P6.4 ADD warranty alert to dashboard
    Show count of warranties expiring in 30 days
    Link to warranty claims list

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 7 — Shipping & Customs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P7.1 CREATE models/shipment.py
    class Shipment:
        id, tenant_id,
        source_type ('sale', 'purchase'), source_id,
        carrier_name, tracking_number, tracking_url,
        shipping_cost, customs_duty, insurance,
        status ('pending', 'shipped', 'in_transit', 'delivered', 'returned'),
        estimated_delivery, actual_delivery,
        recipient_name, recipient_phone, recipient_address

P7.2 MODIFY models/sale.py
    shipping_cost already exists — ensure it links to Shipment if applicable

P7.3 CREATE services/shipment_service.py
    create_shipment(source_type, source_id, carrier, tracking) -> Shipment
    update_status(shipment_id, status) -> None
    get_shipments_for_sale(sale_id) -> list

P7.4 ADD to sale view template
    Show shipment tracking info if exists
    Button to add tracking number

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NO column removal — only additions + aliases + computed properties
2. NO breaking API changes — keep amount_aed as alias for amount_base
3. All changes tested before next phase begins
4. No inline CSS/JS in templates
5. SQLite compatible: JSONB → Text with JSON serialization
6. Default industry = 'general' — no extra fields shown
7. English industry_code (stable), Arabic/English display names
8. No external integrations (email, captcha, oauth)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INDUSTRY CODES (Stable English Identifiers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

general        — عام / General
automotive     — كراج / قطع غيار سيارات / Automotive
electronics    — إلكترونيات / Electronics
supermarket    — سوبرماركت / Supermarket
pharmacy       — صيدلية / Pharmacy
restaurant     — مطعم / كافيه / Restaurant
construction   — مقاولات / Construction
textile        — أقمشة / ملابس / Textile
jewelry        — مجوهرات / ذهب / Jewelry
retail         — تجارة Retail / Retail
trading        — تجارة عامة / Trading
batteries      — بطاريات / Batteries
mobile_new     — موبايلات جديدة / New Mobile Phones
mobile_used    — موبايلات مستعملة / Used Mobile Phones
mobile_parts   — قطع غيار موبايلات / Mobile Spare Parts
clothing       — ملابس / Clothing

Each maps to: field_name_ar, field_name_en for display.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 8 — Serial, IMEI & Warehouse-Level Tracking
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P8.1 ALTER models/product_serial.py
    Add: warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)
    Add: imei1 = db.Column(db.String(15), nullable=True, index=True)
    Add: imei2 = db.Column(db.String(15), nullable=True, index=True)
    Add: model_number = db.Column(db.String(50), nullable=True)
    Add: iccid = db.Column(db.String(20), nullable=True)
    Relationship: warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])
    Unique: (tenant_id, imei1) where imei1 is not null
    Unique: (tenant_id, serial_number)

P8.2 CREATE services/serial_tracking_service.py
    assign_serial_to_warehouse(serial_id, warehouse_id) -> None
    get_serials_in_warehouse(warehouse_id, status='available') -> list
    get_serial_by_imei(imei, tenant_id) -> ProductSerial or None
    transfer_serial(serial_id, from_warehouse_id, to_warehouse_id) -> None
    validate_imei(imei) -> bool (Luhn check for IMEI)

P8.3 ALTER ProductWarehouseStock (from P1.1)
    Add columns for per-warehouse overrides:
      warehouse_barcode = db.Column(db.String(100), nullable=True)
      warehouse_description_ar = db.Column(db.Text, nullable=True)
      warehouse_description_en = db.Column(db.Text, nullable=True)
      warehouse_country_of_origin = db.Column(db.String(100), nullable=True)
    These override Product-level values when not null.

P8.4 MODIFY routes/warehouse.py
    In stock view: show warehouse-specific barcode, description, origin if set.
    In stock transfer: handle serial numbers (move with serial tracking).

P8.5 MODIFY templates/warehouse/index.html
    Display serial/IMEI columns when product.has_serial_number is true.
    Show warehouse-specific descriptions and barcodes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 9 — Product Images with Specs & Dimensions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P9.1 CREATE models/product_image.py
    class ProductImage:
        id, tenant_id, product_id
        image_url = db.Column(db.String(500), nullable=False)
        image_type = db.Column(db.String(20), default='main')
        # image_type values: 'main', 'specs', 'dimensions', 'angle_front', 'angle_back',
        #                    'detail', 'packaging', 'warranty_card', 'receipt'
        caption_ar = db.Column(db.String(200))
        caption_en = db.Column(db.String(200))
        sort_order = db.Column(db.Integer, default=0)
        is_active = db.Column(db.Boolean, default=True)
        created_at
    Index: (product_id, image_type, sort_order)

P9.2 CREATE services/product_image_service.py
    upload_image(product, file, image_type, caption_ar, caption_en) -> ProductImage
    get_images_for_product(product_id, image_type=None) -> list
    reorder_images(product_id, ordered_ids) -> None
    delete_image(image_id) -> None
    validate_image_dimensions(file, min_width=400, min_height=400) -> bool

P9.3 MODIFY routes/products.py
    Add upload endpoints for product images (multipart/form-data).
    Accept image_type in upload form.
    Support multiple image upload.

P9.4 MODIFY templates/products/create.html + edit.html
    Add image upload section after basic fields.
    Show uploaded images as thumbnails with drag-to-reorder.
    Allow setting image_type per upload.
    Display main image in product view.

P9.5 MODIFY templates/products/view.html
    Show image gallery with main image prominent.
    Show specs/dimensions images in tabs.

P9.6 MODIFY storefront (shop)
    Show product images in shop product listing.
    Show image gallery on product detail page.
    Use main image as thumbnail.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with comprehensive tests
2. Migration scripts for all schema changes
3. Updated seed script for industry field definitions
4. No inline CSS/JS in any touched template
5. Updated docs/unified-inventory-master-report.md with completion status
6. Report any NEW issues discovered during implementation

Execute Phase 1 first. Do not start Phase 2 until Phase 1 tests pass.
Report completion status per phase.

Proceed.
