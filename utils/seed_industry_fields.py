from extensions import db
from models.industry_field_definition import IndustryFieldDefinition
from utils.db_safety import atomic_transaction


CORE_FIELDS = [
    ('name', 'الاسم', 'Name', 'text'),
    ('name_ar', 'الاسم العربي', 'Arabic Name', 'text'),
    ('sku', 'رمز المنتج', 'SKU', 'text'),
    ('barcode', 'باركود', 'Barcode', 'text'),
    ('cost_price', 'سعر التكلفة', 'Cost Price', 'number'),
    ('regular_price', 'السعر العادي', 'Regular Price', 'number'),
    ('current_stock', 'المخزون الحالي', 'Current Stock', 'number'),
    ('min_stock_alert', 'تنبيه المخزون المنخفض', 'Min Stock Alert', 'number'),
    ('category_id', 'معرف الفئة', 'Category ID', 'text'),
    ('unit', 'الوحدة', 'Unit', 'text'),
    ('is_active', 'نشط', 'Is Active', 'boolean'),
    ('has_serial_number', 'يتطلب سيريال', 'Has Serial Number', 'boolean'),
    ('warranty_days', 'أيام الضمان', 'Warranty Days', 'number'),
]

INDUSTRY_FIELDS = {
    'batteries': [
        ('battery_type', 'نوع البطارية', 'Battery Type', 'text'),
        ('voltage', 'الجهد', 'Voltage', 'number'),
        ('capacity_ah', 'السعة (أمبير)', 'Capacity (Ah)', 'number'),
        ('cold_cranking_amps', 'أمبير التشغيل البارد', 'Cold Cranking Amps', 'number'),
        ('dimensions', 'الأبعاد', 'Dimensions', 'text'),
        ('terminal_type', 'نوع الطرفية', 'Terminal Type', 'text'),
        ('application', 'التطبيق', 'Application', 'text'),
    ],
    'mobile_new': [
        ('imei_required', 'يتطلب IMEI', 'IMEI Required', 'boolean'),
        ('storage_gb', 'السعة (GB)', 'Storage (GB)', 'number'),
        ('color', 'اللون', 'Color', 'text'),
        ('model_year', 'سنة الموديل', 'Model Year', 'number'),
        ('condition', 'الحالة', 'Condition', 'text'),
        ('warranty_period', 'فترة الضمان', 'Warranty Period', 'number'),
    ],
    'mobile_used': [
        ('condition', 'الحالة', 'Condition', 'text'),
        ('grade', 'الدرجة', 'Grade', 'select'),
        ('battery_health_pct', 'صحة البطارية %', 'Battery Health %', 'number'),
        ('original_box', 'العلبة الأصلية', 'Original Box', 'boolean'),
        ('charger_included', 'شاحن مرفق', 'Charger Included', 'boolean'),
        ('scratches_level', 'مستوى الخدوش', 'Scratches Level', 'select'),
    ],
    'mobile_parts': [
        ('compatible_models', 'الموديلات المتوافقة', 'Compatible Models', 'text'),
        ('part_type', 'نوع القطعة', 'Part Type', 'text'),
        ('oem_or_aftermarket', 'أصلي أو بديل', 'OEM or Aftermarket', 'select'),
    ],
    'clothing': [
        ('size', 'المقاس', 'Size', 'text'),
        ('color', 'اللون', 'Color', 'text'),
        ('fabric_type', 'نوع القماش', 'Fabric Type', 'text'),
        ('season', 'الموسم', 'Season', 'select'),
        ('style_code', 'رمز التصميم', 'Style Code', 'text'),
        ('brand', 'العلامة التجارية', 'Brand', 'text'),
        ('care_instructions', 'تعليمات العناية', 'Care Instructions', 'text'),
    ],
    'automotive': [
        ('car_make', 'الشركة المصنعة', 'Car Make', 'text'),
        ('car_model', 'الموديل', 'Car Model', 'text'),
        ('year', 'السنة', 'Year', 'number'),
        ('engine_cc', 'سعة المحرك', 'Engine CC', 'number'),
        ('transmission', 'ناقل الحركة', 'Transmission', 'select'),
        ('fuel_type', 'نوع الوقود', 'Fuel Type', 'select'),
    ],
    'supermarket': [
        ('expiry_date', 'تاريخ الانتهاء', 'Expiry Date', 'date'),
        ('weight_kg', 'الوزن (كغ)', 'Weight (kg)', 'number'),
        ('organic', 'عضوي', 'Organic', 'boolean'),
        ('halal_certified', 'حلال معتمد', 'Halal Certified', 'boolean'),
        ('batch_number', 'رقم الدفعة', 'Batch Number', 'text'),
    ],
    'electronics': [
        ('device_type', 'نوع الجهاز', 'Device Type', 'text'),
        ('storage_gb', 'السعة (GB)', 'Storage (GB)', 'number'),
        ('color', 'اللون', 'Color', 'text'),
        ('screen_size', 'حجم الشاشة', 'Screen Size', 'number'),
        ('battery_mah', 'بطارية (mAh)', 'Battery (mAh)', 'number'),
    ],
    'pharmacy': [
        ('expiry_date', 'تاريخ الانتهاء', 'Expiry Date', 'date'),
        ('batch_number', 'رقم الدفعة', 'Batch Number', 'text'),
        ('prescription_required', 'يتطلب وصفة طبية', 'Prescription Required', 'boolean'),
        ('storage_temp', 'درجة الحرارة المطلوبة', 'Storage Temperature', 'text'),
    ],
    'construction': [
        ('material_type', 'نوع المادة', 'Material Type', 'text'),
        ('unit_type', 'نوع الوحدة', 'Unit Type', 'text'),
        ('grade', 'الدرجة', 'Grade', 'text'),
        ('supplier_cert', 'شهادة المورد', 'Supplier Cert', 'text'),
    ],
    'textile': [
        ('fabric_type', 'نوع القماش', 'Fabric Type', 'text'),
        ('color', 'اللون', 'Color', 'text'),
        ('size_chart', 'جدول المقاسات', 'Size Chart', 'text'),
        ('origin_country', 'بلد المنشأ', 'Origin Country', 'text'),
    ],
    'jewelry': [
        ('metal_type', 'نوع المعدن', 'Metal Type', 'text'),
        ('purity_karat', 'العيار', 'Purity (Karat)', 'number'),
        ('weight_gram', 'الوزن (غ)', 'Weight (g)', 'number'),
        ('gem_type', 'نوع الحجر', 'Gem Type', 'text'),
    ],
}


def seed_industry_fields():
    with atomic_transaction("seed_industry_fields"):
        order = 0
        for field_code, name_ar, name_en, field_type in CORE_FIELDS:
            existing = IndustryFieldDefinition.query.filter_by(
                industry_code='core', field_code=field_code
            ).first()
            if not existing:
                db.session.add(IndustryFieldDefinition(
                    industry_code='core',
                    field_code=field_code,
                    field_name_ar=name_ar,
                    field_name_en=name_en,
                    field_type=field_type,
                    applies_to='product',
                    sort_order=order,
                ))
            order += 1

        for industry_code, fields in INDUSTRY_FIELDS.items():
            order = 0
            for field_code, name_ar, name_en, field_type in fields:
                existing = IndustryFieldDefinition.query.filter_by(
                    industry_code=industry_code, field_code=field_code
                ).first()
                if not existing:
                    db.session.add(IndustryFieldDefinition(
                        industry_code=industry_code,
                        field_code=field_code,
                        field_name_ar=name_ar,
                        field_name_en=name_en,
                        field_type=field_type,
                        applies_to='product',
                        sort_order=order,
                    ))
                order += 1
