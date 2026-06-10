# ملاحظات فحص يدوي: templates/base.html

تاريخ الفحص: 2026-06-10
عدد الأسطر: 1802
الحجم: 87.6 KB

## هيكل الملف (12 جزء رئيسي)

| الجزء | الأسطر | السطور | الوصف |
|---|---|---|---|
| 1. head | 1-104 | 104 | DOCTYPE, meta, CSS preload, JSON-LD |
| 2. navbar | 106-241 | 136 | main-header navbar كامل |
| 3. fxModal | 243-276 | 34 | modal أسعار الصرف |
| 4. sidebar | 278-913 | 636 | aside sidebar + 40+ menu item |
| 5. content-wrapper | 916-956 | 41 | content-header + flash messages + content block |
| 6. footer | 958-1044 | 87 | footer + mobile nav |
| 7. inline JS (globals) | 1047-1052 | 6 | APP_ENUMS, CURRENT_USER_PERMISSIONS |
| 8. external JS | 1054-1080 | 27 | jQuery, Bootstrap, AdminLTE, plugins |
| 9. calculator modal | 1082-1129 | 48 | navbarCalculatorModal |
| 10. inline JS (massive) | 1131-1795 | 665 | CSRF, prefetch, FX, calculator, error catcher |
| 11. form_validation.js | 1798 | 1 | standalone script tag |
| 12. close | 1800-1802 | 3 | /body, /html |

## ملاحظات Critical

### N1: inline JavaScript 665 سطر (1131-1795)
- لا يمكن cache من قبل المتصفح
- يُعاد تحميله في كل طلب
- يحتوي على 8 وحدات منطقية منفصلة:
  1. CSRF token setup (jQuery.ajaxSetup)
  2. Link prefetch on hover
  3. Flash messages auto-hide (40s timer)
  4. Date/time display updater (1s interval)
  5. FX rates loader + display + cache
  6. Navbar calculator (classic + financial + scientific)
  7. Frontend error catcher (window.onerror, unhandledrejection, fetch wrapper, jQuery.ajaxError, PerformanceObserver longtask + layout-shift)
  8. Theme state audit + MutationObserver
  9. View mode toggle (desktop/mobile/auto)

### N2: sidebar 636 سطر — أكبر جزء
- 40+ menu item مع فحوصات permission مكررة
- هيكل: user panel → nav-treeview لكل قسم
- كل menu item يُكرر نفس نمط if/endif

### N3: dupe integrity attribute (سطر 1067)
```html
<script defer src="https://cdn.jsdelivr.net/npm/sweetalert2@11"
  integrity="sha384-...G/2" crossorigin="anonymous"
  integrity="sha384-...G/2" crossorigin="anonymous">
```
نفس السمة integrity و crossorigin مكررة مرتين.

### N4: noscript fallback يكرر كل شيء
- 10 link tags مكررة داخل noscript
- يمكن تبسيط باستخدام مجموعة CSS واحدة

### N5: jQuery dependency في inline JS
- `$.ajaxSetup` (سطر 1137)
- `$('#fxModal').on('show.bs.modal', ...)` (سطر 1320)
- `window.jQuery(document).ajaxError(...)` (سطر 1651)
- يفترض أن jQuery محمل قبل السطر 1131 (صحيح — jQuery عند 1054)

### N6: PerformanceObserver غير مدعوم في كل المتصفحات
- longtask (سطر 1671)
- layout-shift (سطر 1692)
- wrapped في try/catch — جيد

### N7: form_validation.js في النهاية
- بعد 665 سطر من inline JS
- يجب أن يكون مع باقي الـ defer scripts (قبل 1080)

### N8: محتوى head كبير
- 104 سطر قبل أي محتوى
- JSON-LD schema 22 سطر — يمكن نقله إلى partial
- preload CSS مع onload — يحتاج noscript fallback (موجود لكنه مكرر)

## ملاحظات High

### H1: permission checks مكررة في sidebar
```jinja2
{% if current_user.is_authenticated and current_user.has_permission('manage_sales') %}
```
هذا النمط يتكرر 40+ مرة. يمكن تبسيطه بمتغيرات.

### H2: mobile nav يكرر روابط موجودة في sidebar
- 5 روابط مكررة (dashboard, sales, purchases, products, reports)

### H3: fxModal + calculatorModal خارج content-wrapper
- موجودان في body مباشرة وليس داخل أي wrapper
- يجب نقلهما إلى modals partial

### H4: `{% set is_global_scope_user = ... %}` (سطر 108)
- متغير sidebar يُعرّف في بداية body
- يُستخدم فقط في navbar و sidebar

## ملاحظات Medium

### M1: mixed quotes in extends
- بعض القوالب تستخدم `"base.html"` وأخرى تستخدم `'base.html'`

### M2: `adminlte/js/adminlte.min.js` (سطر 1056)
- يُحمّل قبل الـ defer scripts
- يجب أن يكون `defer` أيضاً

### M3: `window.APP_ENUMS` و `window.CURRENT_USER_PERMISSIONS`
- inline JS يعرّف globals
- يُستخدم `window.hasPermission = function(...)` — يمكن نقله إلى app.js

## ملاحظات Low

### L1: تعليقات داخل inline JS
- "CSRF: attach token to all jQuery AJAX requests"
- "Global Performance Enhancements"
- "تحديث الساعة والتاريخ وسعر الصرف"
- "أسعار صرف حية"

### L2: blank lines كثيرة
- أسطر فارغة بين كل section
- مثال: أسطر 67, 78, 80, 104, 242, 277, 957, 1046, 1047

### L3: `data-fallback` attribute على صورة footer
```html
onerror="if(this.dataset.fallback){this.onerror=null;this.src=this.dataset.fallback;}"
```
- inline event handler — يمكن نقله إلى JS

## توصيات التجزئة المُقترحة

بناءً على هذا الفحص، base.html يجب أن يُجزأ إلى:

```
base.html (target: ~150 سطر)
├── _head.html (104 سطر)
├── _navbar.html (136 سطر)
├── _sidebar.html (636 سطر)
├── _content_wrapper.html (41 سطر)
├── _footer.html (87 سطر)
├── _modals.html (82 سطر: fxModal + calculator)
└── _scripts.html (692 سطر: external + inline JS + form_validation)
```

الـ inline JS (665 سطر) يجب أن يُنقل إلى `static/js/base-helpers.js`.
