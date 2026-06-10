# قائمة المهام القابلة للتنفيذ

## المرحلة 1: Critical

### C1 - تجزئة base.html
- [ ] إنشاء `templates/partials/navbar.html` (~150 سطر)
- [ ] إنشاء `templates/partials/sidebar.html` (~400 سطر)
- [ ] إنشاء `templates/partials/footer.html`
- [ ] إنشاء `templates/partials/modals.html` (fxModal, calculator)
- [ ] إنشاء `templates/partials/scripts.html`
- [ ] تعديل `base.html` لـ `{% include %}` الأجزاء الجديدة
- [ ] تقليص `base.html` إلى ~200 سطر
- **الاعتماديات**: لا توجد

### C2 - نقل inline JS من base.html
- [ ] إنشاء `static/js/base-helpers.js`
- [ ] نقل CSRF handler (~20 سطر)
- [ ] نقل sidebar direction toggle (~30 سطر)
- [ ] نقل theme switcher (~50 سطر)
- [ ] نقل FX rates loader (~80 سطر)
- [ ] نقل calculator logic (~100 سطر)
- [ ] نقل print helpers (~150 سطر)
- [ ] نقل keyboard shortcuts (~100 سطر)
- [ ] إضافة `defer` للملف الجديد في base.html
- [ ] حذف inline JS من base.html
- **الاعتماديات**: C1 (لاستخدام `{% include 'partials/scripts.html' %}`)

### C3 - تبسيط events.py
- [ ] إنشاء `services/branch_gl_service.py`
- [ ] نقل `_ensure_branch_liquidity_account()` إلى service
- [ ] نقل `register_branch_listeners()` إلى service
- [ ] إنشاء `services/gl_auto_service.py`
- [ ] نقل `register_gl_listeners()` إلى service
- [ ] تقليص `events.py` إلى ~200 سطر (logging فقط)
- [ ] تحديث `app.py` لاستدعاء services بدلاً من events
- **الاعتماديات**: لا توجد

### C4 - إصلاح GLAccount infinite recursion
- [ ] إضافة `max_depth` parameter لـ `get_children_recursive()`
- [ ] إضافة `visited` set لتتبع الحلقات
- [ ] إضافة `max_depth=10` في `get_balance()`
- [ ] كتابة test لـ depth limit
- [ ] كتابة test لـ circular reference detection
- **الاعتماديات**: لا توجد

## المرحلة 2: High

### H1 - إزالة inline CSS من القوالب
- [ ] إنشاء `static/css/sales-index.css` (من `sales/index.html` inline CSS)
- [ ] إنشاء `static/css/sales-create.css` (من `sales/create.html`)
- [ ] إنشاء `static/css/customers-statement.css`
- [ ] إنشاء `static/css/invoices-print.css` (دمج 5 قوالب)
- [ ] حذف `<style>` blocks من القوالب
- [ ] إضافة `{% block extra_css %}` في القوالب
- **الاعتماديات**: لا توجد

### H2 - إزالة inline JS من القوالب
- [ ] إنشاء `static/js/sales-index.js`
- [ ] إنشاء `static/js/sales-create.js`
- [ ] إنشاء `static/js/customers-edit.js`
- [ ] حذف `<script>` blocks inline من القوالب
- [ ] إضافة `{% block extra_js %}` في القوالب
- **الاعتماديات**: H1 (نفس القوالب)

### H3 - تقسيم cheque.py
- [ ] إنشاء `services/cheque_service.py`
- [ ] نقل `validate_cheque()` إلى service
- [ ] نقل `calculate_status()` إلى service
- [ ] نقل `process_cheque()` إلى service
- [ ] تقليص `models/cheque.py` إلى Model فقط (~200 سطر)
- [ ] تحديث routes لاستخدام service
- **الاعتماديات**: لا توجد

### H4 - إصلاح Circular Imports
- [ ] إنشاء `models/_constants.py` للـ GL_CONCEPT_REGISTRY
- [ ] نقل `GL_CONCEPT_REGISTRY` من `gl.py`
- [ ] إعادة ترتيب imports في `models/__init__.py`
- [ ] استخدام lazy imports بشكل متسق
- [ ] إزالة `from models import *` داخل الدوال
- **الاعتماديات**: لا توجد

### H5 - تحديث Font Awesome
- [ ] ترقية CDN إلى Font Awesome 6 Free
- [ ] البحث عن `fas fa-` المتغيرة في FA6
- [ ] تحديث `fa` -> `fa-solid`
- [ ] تحديث القوالب التي تستخدم أيقونات محذوفة
- [ ] اختبار rendering
- **الاعتماديات**: C1 (لاختبار في base.html)

### H6 - التخطيط لترقية Bootstrap
- [ ] تحليل التغييرات بين BS4 و BS5
- [ ] تحليل تأثير RTL في BS5
- [ ] تقدير جهد الترقية
- [ ] قرار: الترقية أو البقاء
- **الاعتماديات**: لا توجد

### H7 - إصلاح preload CSS
- [ ] استبدال `<link rel="preload" ... onload>` بـ `<link rel="stylesheet">`
- [ ] أو: تحسين noscript fallback
- [ ] اختبار بدون JavaScript
- **الاعتماديات**: C1

### H8 - بناء Asset Pipeline
- [ ] إنشاء `scripts/build_assets.py`
- [ ] استخدام `jsmin` و `rcssmin`
- [ ] إنشاء `.gz` files باستخدام `gzip`
- [ ] إضافة hash للـ cache busting
- [ ] إضافة command `flask build-assets`
- **الاعتماديات**: لا توجد

## المرحلة 3: Medium

### M1 - توحيد قوالب الطباعة
- [ ] إنشاء `templates/partials/print_header.html`
- [ ] إنشاء `templates/partials/print_footer.html`
- [ ] إنشاء `templates/partials/print_styles.html`
- [ ] تعديل `invoices/classic.html` لـ include partials
- [ ] تعديل `invoices/modern.html` لـ include partials
- [ ] تعديل `invoices/minimal.html` لـ include partials
- [ ] تعديل `invoices/gulf.html` لـ include partials
- [ ] تعديل `invoices/simple.html` لـ include partials
- [ ] نفس العمل لـ receipts/
- **الاعتماديات**: H1

### M2 - دمج landing.html
- [ ] تعديل `public/landing.html` لدعم اللغتين
- [ ] استخدام `{% if current_language == 'en' %}`
- [ ] حذف `public/landing_en.html`
- [ ] تحديث routes
- **الاعتماديات**: لا توجد

### M3 - تحميل شرطي DataTables
- [ ] إنشاء `templates/partials/datatables_assets.html`
- [ ] تعديل القوالب التي تحتاج DataTables لـ include
- [ ] إزالة DataTables من base.html
- **الاعتماديات**: C1

### M4 - تحميل شرطي Select2
- [ ] إنشاء `templates/partials/select2_assets.html`
- [ ] تعديل القوالب التي تحتاج Select2 لـ include
- [ ] إزالة Select2 من base.html (أو الإبقاء إذا مستخدم في كل مكان)
- **الاعتماديات**: C1

### M5 - مراجعة models بدون علاقات
- [ ] مراجعة `tenant.py` - هل يحتاج علاقات؟
- [ ] مراجعة `ai.py` - هل يحتاج علاقات؟
- [ ] مراجعة `store_payment_method.py`
- [ ] مراجعة `card_payment.py`
- [ ] مراجعة `donation.py`
- **الاعتماديات**: لا توجد

### M6 - نقل Product.get_cost()
- [ ] إنشاء `services/product_service.py`
- [ ] نقل `get_cost()` إلى service
- [ ] نقل `get_stock()` إلى service
- [ ] تحديث routes لاستخدام service
- **الاعتماديات**: لا توجد

### M7 - تجزئة support.html
- [ ] تحليل محتوى `support.html` (116.7 KB)
- [ ] إنشاء `templates/partials/support_*.html`
- [ ] تعديل `support.html` لـ include
- **الاعتماديات**: C1

### M8 - دمج owner/base.html
- [ ] تحليل `owner/base.html`
- [ ] دمحه في `base.html` أو إبقائه
- **الاعتماديات**: C1

### M9 - SweetAlert2 fallback
- [ ] إضافة ملف محلي `static/js/sweetalert2.min.js`
- [ ] تعديل base.html لتحميل المحلي إذا فشل CDN
- **الاعتماديات**: C1

### M10 - تحسين fonts
- [ ] إضافة `font-display: swap` لـ Google Fonts
- [ ] أو: self-host Tajawal font
- **الاعتماديات**: C1

### M11 - تقليص erp-theme.css
- [ ] استخراج critical CSS (~5 KB)
- [ ] inline في base.html head
- [ ] تحميل الباقي بشكل non-blocking
- **الاعتماديات**: C1

### M12 - إزالة/دمج accessibility.css
- [ ] تحديد إذا accessibility.css مستخدم
- [ ] إذا مستخدم: دمج في erp-theme.css
- [ ] إذا غير مستخدم: إزالة
- **الاعتماديات**: لا توجد

## المرحلة 4: Low

### L1-L3 - تنظيف التعليقات والمسافات
- [ ] إزالة تعليقات من `models/__init__.py`
- [ ] إزالة تعليقات من `models/events.py`
- [ ] إزالة blank lines الزائدة من `base.html`
- **الاعتماديات**: C3, C1

### L4 - إصلاح dupe integrity
- [ ] إصلاح السطر 1067 في `base.html`
- [ ] إزالة dupe `integrity` و `crossorigin` في SweetAlert2
- **الاعتماديات**: C1

### L5 - إزالة base.html.bak
- [ ] حذف `templates/base.html.bak`
- **الاعتماديات**: لا توجد

### L6-L8 - دمج ملفات CSS
- [ ] دمج `print.css` و `print.min.css`
- [ ] دمج `sales.css` و `sales.min.css`
- [ ] دمج `reports-print.css` و `reports-print.min.css`
- **الاعتماديات**: H8

### L9-L11 - إزالة/دمج ملفات JS صغيرة
- [ ] دمج `shop-storefront.js` في `shop.js`
- [ ] دمج `landing.js` في inline
- [ ] دمج `auth.js` في inline
- **الاعتماديات**: C2

### L12-L15 - إزالة/دمج CSS صغيرة
- [ ] إزالة/دمج `import.css`
- [ ] دمج `select2-enhanced.css` في erp-theme.css
- [ ] دمج `owner-panels.css` في erp-theme.css
- [ ] دمج `notes.css` و `notes.min.css`
- **الاعتماديات**: H8

## الاختبارات

### Tests لـ Critical
- [ ] test_base_html_fragmented: التأكد من include partials
- [ ] test_base_helpers_js_loaded: التأكد من تحميل base-helpers.js
- [ ] test_events_simplified: التأكد من أن events.py < 250 سطر
- [ ] test_gl_no_infinite_recursion: التأكد من max_depth
- [ ] test_gl_circular_detection: التأكد من visited set

### Tests لـ High
- [ ] test_no_inline_css: التأكد من عدم وجود `<style>` في sales/index.html
- [ ] test_no_inline_js: التأكد من عدم وجود inline JS في sales/create.html
- [ ] test_cheque_service_exists: التأكد من وجود cheque_service.py
- [ ] test_no_circular_imports: التأكد من عدم وجود circular imports
- [ ] test_fontawesome_6: التأكد من تحميل FA 6
- [ ] test_stylesheet_not_preload: التأكد من استخدام stylesheet
- [ ] test_minified_updated: التأكد من أن minified files محدثة

### Tests لـ Medium
- [ ] test_print_partials: التأكد من include print partials
- [ ] test_datatables_conditional: التأكد من عدم تحميل DataTables في dashboard
- [ ] test_select2_conditional: التأكد من عدم تحميل Select2 في login
- [ ] test_product_service: التأكد من وجود product_service.py

### Tests لـ Low
- [ ] test_no_comments_in_init: التأكد من عدم وجود تعليقات
- [ ] test_no_blank_lines: التأكد من عدم وجود blank lines زائدة
- [ ] test_no_bak_file: التأكد من حذف base.html.bak

---
