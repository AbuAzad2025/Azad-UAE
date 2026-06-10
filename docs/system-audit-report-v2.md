# تقرير فحص شامل (تحديث 2) — نظام أزاد ERP

## 1. هيكل القوالب (Templates) — تحديث

### 1.1 القوالب الأساسية (Base Templates)

| القالب | السطور | الحجم | الوصف |
|---|---|---|---|
| `base.html` | 1802 | 87.6 KB | القالب الرئيسي — ALL sections inline |
| `shop/base.html` | 181 | 10.6 KB | **قالب مستقل** — لا يُرث base.html |
| `owner/base.html` | 40 | 1.9 KB | يُرث base.html + يضيف BS5 icons + modal fix |

### 1.2 مجلد partials/ — الواقع الحالي

`templates/partials/` يحتوي على **6 ملفات فقط** — لا يوجد navbar أو sidebar partials:

| الملف | السطور | الوصف |
|---|---|---|
| `financial_filter_bar.html` | 56 | 3 macros: filter_bar, kpi_cards, report_header |
| `flask_pagination.html` | 24 | pagination macro |
| `print_developer_footer.html` | 12 | footer للطباعة |
| `print_tenant_logo.html` | 11 | logo للمستندات |
| `print_unified_amount_qr.html` | 26 | المبلغ بالحروف + QR |
| `print_unified_banner.html` | 18 | banner الطباعة |

**الملاحظة الحاسمة**: القوالب `invoices/*.html` و `receipts/*.html` تستخدم `{% include %}` للـ partials (3 includes لكل قالب). أما باقي 235 قالباً يُرثون `base.html` مباشرة دون أي partials.

### 1.3 الـ blocks في base.html — استخداماتهم

| Block | تعريف | الاستخدام | ملاحظة |
|---|---|---|---|
| `title` | base.html:5 | 236 ملف | كل القوالب تقريباً |
| `meta_description` | base.html:16 | 0 خارج base | نادر الاستخدام |
| `meta_keywords` | base.html:17 | 0 خارج base | نادر الاستخدام |
| `robots` | base.html:19 | 0 خارج base | نادر الاستخدام |
| `og_type` | base.html:23 | 0 خارج base | نادر الاستخدام |
| `og_title` | base.html:25 | 0 خارج base | نادر الاستخدام |
| `og_description` | base.html:26 | 0 خارج base | نادر الاستخدام |
| `extra_css` | base.html:78 | 70 ملف | جيد |
| `page_title` | base.html:919 | 124 ملف | جيد |
| `content` | base.html:953 | 235 ملف | الجميع |
| `extra_js` | base.html:1080 | 67 ملف | جيد |

**المشكلة**: الـ blocks `meta_description`, `meta_keywords`, `robots`, `og_*` نادراً ما تُستخدم خارج base.html — يعني كل صفحة تحصل على نفس الـ SEO metadata.

### 1.4 shop/base.html — قالب مستقل تماماً

`shop/base.html` لا يُرث `base.html` أبداً. يستخدم stack كامل مختلف:

| المكوّن | base.html | shop/base.html |
|---|---|---|
| Bootstrap | 4.6.2 (CDN) | غير مذكور (custom CSS) |
| Font Awesome | 5.15.4 (CDN) | **6.5.1 (CDN)** |
| الخط | Tajawal (Google) | IBM Plex Sans Arabic (Google) |
| CSS الرئيسي | erp-theme.css | **shop-palestine.css** |
| AdminLTE | ✅ | ❌ |
| Select2 | ✅ | ❌ |
| DataTables | ✅ | ❌ |
| SweetAlert2 | ✅ | ❌ |

**التأثير**: المتجر يستخدم إصدار Font Awesome أحدث من باقي النظام (6.5.1 مقابل 5.15.4). هذا يعني أن أي أيقونة FA5 قد لا تعمل في المتجر إذا تمت مشاركة القوالب.

### 1.5 owner/base.html — وراثة إضافية محدودة

`owner/base.html` (40 سطر) يُرث `base.html` ويضيف:
1. bootstrap-icons 1.11.3 (CDN)
2. inline CSS لـ `.btn-close` (BS5 style)
3. inline JS لتحويل `data-bs-toggle` إلى `data-toggle` (توافق BS4→BS5)

يُستخدم في **3 قوالب فقط**:
- `owner/tenant_create.html`
- `owner/tenant_edit.html`
- `owner/tenants_list.html`

### 1.6 هيكل base.html الداخلي (12 جزء)

| الجزء | السطور | الحجم | الوصف |
|---|---|---|---|
| head | 1-104 | 104 | meta, CSS, JSON-LD |
| navbar | 106-241 | 136 | main-header navbar |
| fxModal | 243-276 | 34 | modal أسعار الصرف |
| **sidebar** | **278-913** | **636** | **aside + 40+ menu item** |
| content-wrapper | 916-956 | 41 | content-header + flash + content |
| footer | 958-1044 | 87 | footer + mobile nav |
| inline JS (globals) | 1047-1052 | 6 | APP_ENUMS, PERMISSIONS |
| external JS | 1054-1080 | 27 | jQuery + 16 ملف |
| calculator modal | 1082-1129 | 48 | navbarCalculatorModal |
| **inline JS (massive)** | **1131-1795** | **665** | **CSRF, FX, calculator, error catcher** |
| form_validation.js | 1798 | 1 | standalone |
| close | 1800-1802 | 3 | /body, /html |

### 1.7 inline CSS في القوالب — التحديث

{% block extra_css %} يُستخدم في 70 ملف. منها بعض القوالب تحتوي على inline `<style>`:

| القالب | `<style>` blocks | inline CSS سطور |
|---|---|---|
| `sales/index.html` | 1 | ~80 |
| `sales/create.html` | 1 | ~60 |
| `customers/statement.html` | 1 | ~30 |
| `expenses/print.html` | 1 | ~25 |
| `invoices/classic.html` | 1 | ~50 |
| `invoices/modern.html` | 1 | ~45 |
| `invoices/minimal.html` | 1 | ~40 |
| `invoices/gulf.html` | 1 | ~55 |
| `invoices/simple.html` | 1 | ~35 |
| `receipts/classic.html` | 1 | ~45 |
| `receipts/modern.html` | 1 | ~40 |
| `receipts/minimal.html` | 1 | ~35 |
| `receipts/gulf.html` | 1 | ~50 |
| `receipts/simple.html` | 1 | ~30 |

**الملاحظة**: قوالب الطباعة (10 قوالب) تحتوي على CSS متطابق بنسبة 70%+. partials الموجودة (`print_unified_banner.html`, `print_tenant_logo.html`...) تُستخدم فقط في قوالب الطباعة.

### 1.8 inline JS في القوالب — التحديث

{% block extra_js %} يُستخدم في 67 ملف. منها:

| القالب | `<script>` blocks | inline JS سطور |
|---|---|---|
| `sales/create.html` | 2 | ~200 |
| `sales/index.html` | 1 | ~150 |
| `customers/edit.html` | 1 | ~100 |
| `public/landing.html` | 2 | ~120 |
| `support.html` | 1 | ~80 |

## 2. هيكل المودالز (Models) — تحديث

### 2.1 ملف events.py — التفاصيل

`models/events.py` (1575 سطر) — أكبر ملف في المشروع:

| الوظيفة | السطور | الوصف |
|---|---|---|
| `register_sale_listeners()` | ~200 | after_insert, after_update, after_delete for Sale |
| `register_receipt_listeners()` | ~150 | after_insert, after_update for Receipt |
| `register_purchase_listeners()` | ~150 | after_insert, after_update for Purchase |
| `register_payment_listeners()` | ~150 | after_insert, after_update for Payment |
| `register_branch_listeners()` | ~200 | after_insert for Branch — يُنشئ GL accounts تلقائياً |
| `register_stock_movement_listeners()` | ~100 | after_insert for StockMovement |
| `register_cheque_listeners()` | ~100 | after_insert, after_update for Cheque |
| `register_product_return_listeners()` | ~100 | after_insert for ProductReturn |
| `register_expense_listeners()` | ~100 | after_insert, after_update for Expense |
| `register_gl_listeners()` | ~150 | after_insert, after_update for GLAccount |
| `register_validation_listeners()` | ~100 | validate events |
| `register_audit_listeners()` | ~50 | audit logging |
| `register_ai_listeners()` | ~100 | AI/neural training (gated) |
| `register_neural_training_listeners()` | ~100 | neural training (gated) |

### 2.2 cheque.py — أضخم مودال

`models/cheque.py` (758 سطر):
- يحتوي على 8 relationships
- يحتوي على methods للتحقق (validate), حساب الحالة (calculate_status), المعالجة (process)
- يجب تقسيمه إلى model + service

### 2.3 gl.py — self-referential infinite recursion risk

`models/gl.py` (464 سطر, 20 relationship):
```python
parent = db.relationship('GLAccount', remote_side=[id], backref='children')
```
- `get_children_recursive()` — لا يوجد max_depth
- `get_balance()` — تستدعي نفسها بشكل متكرر

### 2.4 Circular Import Risk — التفاصيل

| الملف | المشكلة | السطر |
|---|---|---|
| `models/gl.py` | `from utils.gl_services import ...` | 4 |
| `models/sale.py` | `from models import GLJournalLine` داخل `get_balance()` | داخل method |
| `models/events.py` | `from models import *` داخل كل method | متكرر |
| `models/purchase.py` | lazy imports داخل methods | متكرر |
| `models/payment.py` | lazy imports داخل methods | متكرر |

## 3. استيراد CSS/JS — تحديث

### 3.1 ملفات CSS في static/css/ — أكبر 15

| الملف | الحجم | ملاحظة |
|---|---|---|
| `erp-theme.css` | 70.3 KB | blocking, كل صفحة |
| `landing.css` | 27.6 KB | صفحة واحدة فقط |
| `accessibility.css` | 27.0 KB | **غير مُحمّل** |
| `shop.css` | 26.8 KB | shop فقط |
| `shop-palestine.css` | 25.9 KB | shop فقط |
| `azad-login.css` | 20.5 KB | login فقط |
| `shop.min.css` | 20.6 KB | minified |
| `statement-print.css` | 14.7 KB | طباعة |
| `reports-print.css` | 10.1 KB | طباعة |
| `landing.min.css` | 8.8 KB | minified |
| `print.min.css` | 6.3 KB | minified |
| `sales.min.css` | 5.9 KB | minified |
| `print.css` | 5.7 KB | طباعة |
| `select2-enhanced.css` | 5.7 KB | select2 |
| `sales.css` | 5.5 KB | مبيعات |

### 3.2 ملفات JS في static/js/ — أكبر 15

| الملف | الحجم | ملاحظة |
|---|---|---|
| `warehouses.js` | 34.1 KB | warehouses |
| `checks.js` | 32.3 KB | cheques |
| `payments.js` | 27.3 KB | payments |
| `shop.js` | 26.9 KB | shop |
| `sales-enhanced.js` | 26.4 KB | sales |
| `azad-app.js` | 25.8 KB | app |
| `smart-print.js` | 22.8 KB | print |
| `app.js` | 22.2 KB | general |
| `payment_form.js` | 20.0 KB | payment form |
| `product-form.js` | 17.5 KB | product form |
| `app.min.js` | 8.8 KB | minified |
| `purchase_form.js` | 8.1 KB | purchase |
| `receipt.js` | 6.8 KB | receipt |
| `pos.js` | 5.5 KB | POS |
| `shop.min.js` | 4.8 KB | minified |

### 3.3 مشاكل CSS/JS المُحدَّثة

| # | المشكلة | التفاصيل |
|---|---|---|
| C1 | inline JS 665 سطر في base.html | 9 وحدات منطقية، لا يمكن cache |
| C2 | dupe integrity في SweetAlert2 | السطر 1067: `integrity="..."` مكررة مرتين |
| H1 | Font Awesome 5.15.4 قديم | shop/base.html يستخدم FA 6.5.1 (أحدث!) |
| H2 | Bootstrap 4.6.2 قديم | لا يدعم BS5 modal attributes |
| H3 | owner/base.html يضيف BS5 modal fix | يدل على BS4→BS5 migration في التقدم |
| H4 | accessibility.css 27 KB غير مُحمّل | ميت |
| H5 | landing.css 27.6 KB في صفحة واحدة | blocking |
| H6 | minified files قد تكون غير محدثة | لا يوجد build pipeline |
| M1 | form_validation.js بعد inline JS | يجب أن يكون مع defer scripts |
| M2 | DataTables 6 ملفات في كل صفحة | لا تُستخدم في كل مكان |
| M3 | Select2 في كل صفحة | قد لا تُستخدم في كل مكان |
| M4 | noscript fallback يكرر 10 روابط | تكرار كامل |

## 4. dependency graphs المُحدَّثة

### 4.1 قوالب Base Templates

```
base.html (1802 سطر)
    ├── extends: 235 قالب مباشر
    │   ├── admin/* (12)
    │   ├── ai/* (2)
    │   ├── branches/* (3)
    │   ├── cheques/* (8)
    │   ├── customers/* (5)
    │   ├── errors/* (3)
    │   ├── expenses/* (7)
    │   ├── gamification/* (1)
    │   ├── invoices/* (5) — print templates
    │   ├── ledger/* (26)
    │   ├── monitoring/* (1)
    │   ├── owner/* (62) — بعضها يُرث owner/base.html
    │   ├── partners/* (7)
    │   ├── payment_vault/* (13)
    │   ├── payments/* (11)
    │   ├── payroll/* (6)
    │   ├── pos/* (2)
    │   ├── printing/* (1)
    │   ├── products/* (6)
    │   ├── public/* (15) — بعضها landing standalone
    │   ├── purchases/* (5)
    │   ├── receipts/* (5) — print templates
    │   ├── reports/* (12)
    │   ├── returns/* (2)
    │   ├── sales/* (6)
    │   ├── shop/* (14) — يُرث shop/base.html (مستقل)
    │   ├── store/* (9)
    │   ├── suppliers/* (5)
    │   ├── users/* (4)
    │   └── warehouse/* (7)
    │
    └── includes: 0 (لا يوجد navbar/sidebar partials)

owner/base.html (40 سطر)
    └── extends: base.html
        └── used by: owner/tenant_create.html, tenant_edit.html, tenants_list.html

shop/base.html (181 سطر) — مستقل تماماً
    └── extends: لا شيء
        └── used by: 14 قالب في shop/*
```

### 4.2 CSS/JS Assets

```
base.html head
    ├── bootstrap@4.6.2 (CDN)
    ├── adminlte.min.css
    ├── erp-theme.css (70.3 KB, blocking)
    └── preload:
        ├── Tajawal font
        ├── Font Awesome 5.15.4
        ├── Select2
        ├── DataTables (2 ملف)
        └── SweetAlert2 CSS

base.html footer
    ├── jquery.min.js (blocking)
    ├── bootstrap.bundle.min.js (blocking)
    ├── adminlte.min.js (blocking)
    ├── select2.full.min.js (defer)
    ├── datatables (6 ملفات, defer)
    ├── sweetalert2@11 (defer)
    ├── i18n.js (defer)
    ├── app.js (defer)
    ├── azad-app.js (defer)
    ├── customer-select.js (defer)
    ├── payment-fields.js (defer)
    ├── delete-manager.js (defer)
    ├── action-helpers.js (defer)
    ├── notifications.js (defer)
    ├── keyboard-shortcuts.js (defer)
    ├── ui-theme.js (defer)
    ├── performance.js (defer)
    ├── smart-print.js (defer)
    └── form_validation.js (NOT defer — after inline JS)

shop/base.html head
    ├── IBM Plex Sans Arabic (Google Fonts)
    ├── Font Awesome 6.5.1 (CDN)
    └── shop-palestine.css

shop/base.html footer
    └── shop-storefront.js (defer)
```

## 5. المشاكل الكاملة (39 مشكلة)

### Critical (4)

| # | المشكلة | الملف | السبب |
|---|---|---|---|
| C1 | base.html 1802 سطر | `templates/base.html` | navbar + sidebar + inline JS كلها في ملف واحد |
| C2 | inline JS 665 سطر | `templates/base.html:1131-1795` | 9 وحدات منطقية، لا يمكن cache |
| C3 | events.py 1575 سطر | `models/events.py` | 13 مجموعة ORM listeners |
| C4 | GLAccount infinite recursion | `models/gl.py` | get_children_recursive() بدون max_depth |

### High (8)

| # | المشكلة | الملف | السبب |
|---|---|---|---|
| H1 | inline CSS في 15+ قالب | `sales/*.html`, `invoices/*.html` | تكرار CSS |
| H2 | inline JS في 10+ قالب | `sales/create.html` | تكرار JS |
| H3 | cheque.py 758 سطر | `models/cheque.py` | business logic في model |
| H4 | Circular Import Risk | `models/gl.py`, `events.py` | lazy imports داخل methods |
| H5 | Font Awesome 5 قديم | `templates/base.html` | shop يستخدم FA 6.5.1 (أحدث) |
| H6 | Bootstrap 4 قديم | `templates/base.html` | owner/base.html يضيف BS5 fix |
| H7 | preload CSS fallback ضعيف | `templates/base.html` | noscript يكرر كل شيء |
| H8 | minified files غير محدثة | `static/js/*.min.js` | لا يوجد build pipeline |

### Medium (12)

| # | المشكلة | الملف | السبب |
|---|---|---|---|
| M1 | قوالب طباعة مكررة | `invoices/*.html`, `receipts/*.html` | 70% CSS متطابق |
| M2 | landing.html و landing_en.html | `public/landing.html` | نسختان بدلاً من قالب واحد |
| M3 | DataTables في كل صفحة | `templates/base.html` | 6 ملفات غير ضرورية |
| M4 | Select2 في كل صفحة | `templates/base.html` | قد لا تُستخدم في كل مكان |
| M5 | models بدون علاقات | `tenant.py`, `ai.py` | 5 مودالز |
| M6 | Product.get_cost() cross-model | `models/product.py` | logic في model |
| M7 | support.html 116.7 KB | `templates/support.html` | ضخم |
| M8 | owner/base.html قليل الاستخدام | `owner/base.html` | 3 قوالب فقط |
| M9 | SweetAlert2 dupe integrity | `templates/base.html:1067` | integrity مكررة |
| M10 | Google Fonts blocking | `templates/base.html` | FOIT |
| M11 | ERP theme CSS كبير | `static/css/erp-theme.css` | 70.3 KB blocking |
| M12 | accessibility.css غير مستخدم | `static/css/accessibility.css` | 27 KB ميت |

### Low (15)

| # | المشكلة | الملف |
|---|---|---|
| L1 | تعليقات في models/__init__.py | `models/__init__.py` |
| L2 | تعليقات في events.py | `models/events.py` |
| L3 | blank lines في base.html | `templates/base.html` |
| L4 | dupe integrity | `templates/base.html:1067` |
| L5 | base.html.bak غير موجود | تم حذفه ✅ |
| L6 | print.css و print.min.css | `static/css/print.css` |
| L7 | sales.css و sales.min.css | `static/css/sales.css` |
| L8 | reports-print.css | `static/css/reports-print.css` |
| L9 | shop-storefront.js صغير | `static/js/shop-storefront.js` |
| L10 | landing.js | `static/js/landing.js` |
| L11 | auth.js | `static/js/auth.js` |
| L12 | import.css | `static/css/import.css` |
| L13 | select2-enhanced.css | `static/css/select2-enhanced.css` |
| L14 | owner-panels.css | `static/css/owner-panels.css` |
| L15 | notes.css | `static/css/notes.css` |
