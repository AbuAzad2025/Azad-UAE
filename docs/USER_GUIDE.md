# دليل استخدام شامل — AZADEXA ERP

## جدول المحتويات

1. [نظرة عامة على النظام](#1-نظرة-عامة)
2. [الدخول والمستخدمين](#2-الدخول-والمستخدمين)
3. [لوحة التحكم الرئيسية](#3-لوحة-التحكم)
4. [نقاط البيع POS](#4-نقاط-البيع-pos)
5. [المبيعات والفواتير](#5-المبيعات)
6. [المخزون والمنتجات](#6-المخزون)
7. [المشتريات](#7-المشتريات)
8. [العملاء](#8-العملاء)
9. [الموردين](#9-الموردين)
10. [المدفوعات والخزينة](#10-المدفوعات)
11. [المصروفات](#11-المصروفات)
12. [الشيكات](#12-الشيكات)
13. [المحاسبة — دفتر الأستاذ العام](#13-المحاسبة)
14. [التقارير](#14-التقارير)
15. [الموارد البشرية والرواتب](#15-الموارد-البشرية)
16. [إدارة علاقات العملاء CRM](#16-crm)
17. [المشاريع](#17-المشاريع)
18. [التذاكر والدعم الفني](#18-التذاكر)
19. [التسويق والبريد الإلكتروني](#19-التسويق)
20. [المتجر الإلكتروني](#20-المتجر)
21. [المساعد الذكي AI](#21-المساعد-الذكي)
22. [الإعدادات والإدارة](#22-الإعدادات)
23. [الصلاحيات والأدوار](#23-الصلاحيات)
24. [الفروع والمتاجر المتعددة](#24-الفروع)
25. [API والتكاملات الخارجية](#25-api)
26. [الأمان والتدقيق](#26-الأمان)

---

## 1. نظرة عامة

AZADEXA ERP هو نظام متكامل لإدارة الموارد المؤسسية، يدعم **تعدد المستأجرين (Multi-Tenant)** مع عزل كامل للبيانات. يغطي المبيعات، المشتريات، المخزون، المحاسبة، الموارد البشرية، إدارة العملاء، المشاريع، نقاط البيع، المتجر الإلكتروني، والمساعد الذكي.

### البنية التقنية (من الكود)
- **إطار العمل:** Flask 3.1 مع SQLAlchemy 2.0
- **قاعدة البيانات:** PostgreSQL (مع SQLite للاختبارات)
- **المحاسبة:** نظام دفتر أستاذ عام مزدوج (Double-Entry GL)
- **التكاليف:** متوسط التكلفة المرجح المتحرك (MWAC) لكل منتج في كل مستودع
- **العملات:** دعم متعدد العملات مع تحويل آلي إلى العملة الأساسية (AED)
- **الفروع:** دعم متعدد الفروع مع تحكم في الوصول للمستودعات
- **العزل:** 4 طبقات حماية (ORM auto-scoping + query helpers + request-level + blueprint guards)
- **الـ API:** REST API (v1/v2) + GraphQL + WebSocket

---

## 2. الدخول والمستخدمين

### صفحة الدخول
- **الرابط:** `/auth/login`
- تدعم اللغتين العربية والإنجليزية
- حماية CSRF مفعلة
- قفل الحساب بعد 5 محاولات فاشلة لمدة 15 دقيقة
- حماية الجلسة بـ `session_protection = "strong"`

### المستخدمون والأدوار
- النظام يدعم 32 نوعاً من الصلاحيات المفصلة (انظر قسم 23)
- الأدوار الأساسية: owner, super_admin, manager, accountant, seller, cashier, warehouse_manager, etc.
- كل مستخدم مرتبط بـ `tenant_id` (شركة) ويمكن ربطه بـ `branch_id` (فرع)

### تسجيل الخروج
- `/auth/logout` — يُلغي الجلسة ويُفرغ ذاكرة التخزين المؤقت

---

## 3. لوحة التحكم

### الرابط
- `/` (الصفحة الرئيسية)

### ما تظهره
- إحصائيات سريعة: عدد العملاء، المنتجات، المبيعات، المشتريات
- تنبيهات المخزون المنخفض
- آخر الفواتير
- الرصيد النقدي
- إشعارات النظام

---

## 4. نقاط البيع POS

> **الملف الرئيسي:** `routes/pos.py` (2726 سطر)
> **الخدمات:** `services/sale_service.py`, `services/pos_cart_service.py`, `services/pos_cash_service.py`, `services/pos_override_service.py`, `services/pos_rma_service.py`, `services/promotion_service.py`

### 4.1 متطلبات التشغيل
- يجب تفعيل `Tenant.enable_pos = True`
- يجب أن يكون للمستخدم صلاحية `manage_sales`

### 4.2 الجلسة (Session)
**النموذج:** `PosSession` — جلسة يومية للكاشير

| الحالة | الوصف |
|--------|-------|
| `open` | الجلسة مفتوحة وقيد الاستخدام |
| `paused` | موقفة مؤقتاً |
| `closed` | مغلقة نهائياً |

**الحقول الرئيسية:**
- `opening_balance_cash` — الرصيد الافتتاحي (عد نقدي فعلي)
- `closing_balance_cash` — الرصيد عند الإغلاق (عد نقدي فعلي)
- `expected_balance` — الرصيد المتوقع حسابياً
- `difference` — الفرق (تقصير / زيادة)
- `total_sales` — إجمالي المبيعات
- `total_cash_sales` — مبيعات نقدية
- `total_card_sales` — مبيعات بالبطاقة

**نقاط النهاية:**
- `POST /pos/api/session/open` — فتح جلسة
- `POST /pos/api/session/pause` — إيقاف مؤقت
- `POST /pos/api/session/resume` — استئناف
- `POST /pos/api/session/close` — إغلاق (يتطلب العد النقدي الفعلي)

**ملاحظة:** عند الإغلاق إذا كان الفرق ≠ 0، يسجل النظام قيد محاسبي تلقائياً (Cash Over/Short).

### 4.3 المناوبات (Shift)
**النموذج:** `PosShift` — مناوبة فرعية داخل الجلسة (ميزة Pro tier فقط)

| الحالة | الوصف |
|--------|-------|
| `open` | مفتوحة |
| `reconciled` | تمت التسوية |
| `closed` | مغلقة |

**نقاط النهاية:**
- `POST /pos/api/shift/open` — فتح مناوبة
- `POST /pos/api/shift/reconcile` — تسوية (عد نقدي فعلي)
- `POST /pos/api/shift/close` — إغلاق

### 4.4 إنشاء فاتورة (Checkout)
**نقطة النهاية:** `POST /pos/api/checkout`

**خطوات العملية:**
1. التحقق من وجود جلسة نشطة
2. التحقق من صلاحية الرمز المميز للجلسة (HMAC) إذا كان الجهاز مربوطاً
3. دعم مفتاح `Idempotency-Key` لمنع الفواتير المكررة
4. التحقق من وجود مناوبة مفتوحة (إذا كانت المناوبات مفعلة)
5. تحديد العميل (walk-in أو عميل موجود)
6. التحقق من صلاحية الوصول للمستودع
7. تحديد العملة وسعر الصرف
8. دمج الأسطر المكررة (نفس المنتج)
9. قفل المنتجات (SELECT ... FOR UPDATE) لمنع التعارض
10. التحقق من الأرقام التسلسلية (إذا كان المنتج يتطلبها)
11. التحقق من السعر — إذا كان السعر المُدخل مختلفاً عن السعر القياسي يتطلب صلاحية `override_sale_price`
12. التحقق من الخصم اليدوي — يتطلب صلاحية `pos_discount_override` أو رمز تفويض مشرف
13. تطبيق العروض الترويجية (إذا كانت مفعلة)
14. معالجة الدفع (دفع واحد أو دفع متعدد)
15. إنشاء الفاتورة في دفتر الأستاذ العام (GL) تلقائياً
16. خصم المخزون وتحديث MWAC
17. إنشاء طلب KDS إذا كان نوع الطلب يدعم المطبخ

### 4.5 أنواع الطلبات (Order Types)
**النموذج:** `PosOrderType`

الأنواع الافتراضية: dine_in, pickup, delivery, online, phone, walk_in

يمكن تفعيل/تعطيل KDS لكل نوع عبر حقل `kds_enabled`.

### 4.6 طاولات وطوابق (Restaurant Mode)
**النماذج:** `PosFloor`, `PosTable`, `PosTableOrder`

**نقاط النهاية:**
- `GET /pos/api/floors` — قائمة الطوابق
- `POST /pos/api/floors/create` — إنشاء طابق
- `GET /pos/api/floors/<id>/tables` — طاولات الطابق
- `POST /pos/api/tables/create` — إنشاء طاولة (سعة، إحداثيات، شكل)
- `POST /pos/api/tables/<id>/status` — تغيير الحالة (free/occupied/reserved)
- `POST /pos/api/tables/<id>/assign` — ربط فاتورة بطاولة

### 4.7 نظام عرض المطبخ KDS
**النموذج:** `PosKdsOrder`

| الحالة | الوصف |
|--------|-------|
| `pending` | في انتظار التحضير |
| `preparing` | قيد التحضير |
| `ready` | جاهز |
| `served` | تم التقديم |
| `cancelled` | ملغي |

**نقاط النهاية:**
- `GET /pos/api/kds/stream` — تدفق SSE (Server-Sent Events) لتحديثات لحظية
- `GET /pos/api/kds/orders` — قائمة الطلبات
- `POST /pos/api/kds/orders/<id>/status` — تحديث الحالة

**شاشة العملاء:**
- `GET /pos/customer-display` — شاشة العملاء
- `GET /pos/api/customer-display/<session_id>/stream` — تدفق SSE للشاشة

### 4.8 العروض الترويجية (Promotions)
**الخدمة:** `PromotionService`

| نوع العرض | الوصف |
|-----------|-------|
| `bundle` | اشترِ N بسعر X |
| `tiered` / `percentage` / `fixed` | خصم حسب الحد الأدنى (كمية/مبلغ) |
| `combo` | اشترِ A+B معاً |
| `bogo` | اشترِ N واحصل على M مجاناً |

**نقطة النهاية:** `POST /api/promotions/evaluate` — معاينة الخصم قبل الدفع

### 4.9 الدفع المتعدد (Split Tender)
- يدعم الدفع بأكثر من طريقة (نقد + بطاقة + نقاط)
- يتطلب ميزة `pos_multi_tender` (Pro tier)
- كل طريقة دفع تُسجل كـ `Payment` مستقل مع ترحيل GL خاص

### 4.10 إرجاع المبيعات (RMA)
**الخدمة:** `PosRmaService`

**نقاط النهاية:**
- `POST /api/returns` — إنشاء إرجاع
- `GET /api/stock/lookup` — البحث عن المخزون حسب المستودع

**طرق الاسترداد:**
- `credit` — رصيد للعميل (افتراضي)
- `cash` — استرداد نقدي من الدرج

### 4.11 الدرج النقدي (Cash Movements)
**الخدمة:** `PosCashService`

| النوع | الوصف |
|-------|-------|
| `pay_in` — إيداع | إيداع نقدي في الدرج |
| `pay_out` — صرف | سحب نقدي من الدرج |

**نقاط النهاية:**
- `GET /api/cash-movements` — قائمة الحركات
- `POST /api/cash-movements` — إنشاء حركة

**ملاحظة:** كل حركة تُرحّل في دفتر الأستاذ العام تلقائياً.

### 4.12 رموز التفويض (Manager Override)
**الخدمة:** `PosOverrideService`

العمليات التي تتطلب تفويض:
- حذف سطر من العربة (`pos_void_line`)
- تطبيق خصم يدوي (`pos_discount_override`)
- فتح الدرج بدون بيع (`pos_no_sale_drawer`)
- إيداع/صرف (`pos_pay_in_out`)

**الآلية:**
1. الكاشير يطلب PIN من المشرف
2. النظام يتحقق من PIN + صلاحية `pos_authorize_override`
3. يُنشأ رمز مميز (Token) صالح لـ 60 ثانية
4. يُستخدم الرمز في الطلب التالي

### 4.13 عربات الانتظار (Parked Carts)
**النموذج:** `PosCart`

- تخزين عربات الشراء على الخادم (ليس localStorage فقط)
- يمكن إيقاف العربة في جهاز واستئنافها في جهاز آخر
- الحد الأقصى: 25 عربة لكل جلسة
- الحد الأقصى للحجم: 48 كيلوبايت

**نقاط النهاية:**
- `POST /api/carts/park` — إيقاف العربة
- `GET /api/carts/<id>` — استئناف (مع قفل SELECT FOR UPDATE)
- `DELETE /api/carts/<id>` — حذف
- `POST /api/carts/<id>/void-line` — حذف سطر

### 4.14 التكامل مع الأجهزة (Hardware Integration)

يدعم POS الأجهزة الطرفية الكاملة لمحطة الكاشير: طابعات حرارية، درج نقدي، ميزان إلكتروني، كاميرا مسح باركود، طرفية دفع، وشاشة عميل — مع عمل كامل دون اتصال بالإنترنت.

#### 4.14.1 بنية التكامل

```
شاشة الكاشير (المتصفح)
   ├── طابعة WebUSB / WebSerial ──────────► اتصال مباشر من المتصفح
   ├── ميزان (Web Serial) ────────────────► قراءة وزن حية داخل الشاشة
   ├── كاميرا (BarcodeDetector) ──────────► مسح باركود بالكاميرا
   └── وكيل الأجهزة المحلي (127.0.0.1:8567) ─► طابعة شبكة TCP:9100 أو تسلسلية + درج
الخادم ─► /pos/api/hardware/* (بروكسي للوكيل) ─► /pos/api/sale/<id>/print-tickets (توزيع التذاكر)
```

**المكوّنات:**

| المكوّن | الملف / المسار | الوظيفة |
|---|---|---|
| وكيل الأجهزة | `scripts/hardware_agent/pos_hardware_agent.py` | جسر محلي للطابعات والدرج عبر ESC/POS |
| إعدادات الطابعات | `/pos/settings/printers` | تعريف الطابعات وأدوارها وتوجيه الفئات |
| توزيع التذاكر | `GET /pos/api/sale/<id>/print-tickets` | تقسيم الفاتورة إلى تذاكر حسب الدور |
| الميزان | `static/js/pos/scale-serial.js` | قراءة الوزن عبر Web Serial |
| الكاميرا | `static/js/barcode-scanner.js` | مسح BarcodeDetector من الشاشة |
| الطباعة المباشرة | `static/js/pos/escpos-printer.js` + `print-tickets.js` | WebUSB/WebSerial بدون وكيل |
| شاشة العميل | SSE + `cfd-broadcast.js` | عرض الفاتورة لحظياً للعميل |

#### 4.14.2 وكيل الأجهزة المحلي (Hardware Agent)

برنامج Python مستقل يعمل على **جهاز الكاشير نفسه** ويستمع على `http://127.0.0.1:8567` (loopback فقط — لا يظهر على الشبكة إطلاقاً). مكتباته القياسية فقط (stdlib)؛ و`pyserial` اختيارية للطابعات التسلسلية.

**التشغيل:**

```bash
python scripts/hardware_agent/pos_hardware_agent.py
```

- تغيير المنفذ: متغير البيئة `POS_HARDWARE_AGENT_PORT`
- للتشغيل التلقائي مع إقلاع Windows: أضف اختصاراً للأمر في مجلد Startup، أو سجّله كخدمة عبر `nssm` / Task Scheduler

**الإعداد الاختياري `agent_config.json`** (بجانب السكربت، أو عبر `POS_HARDWARE_AGENT_CONFIG`): يزوّد `default_printer` عندما لا يحمل الطلب طابعة:

```json
{
  "default_printer": {
    "connection": "network",
    "host": "192.168.1.50",
    "port": 9100,
    "encoding": "cp864"
  }
}
```

**نقاط نهاية الوكيل:**

- `GET /status` — حالة الوكيل وإعداد الطابعة
- `POST /print-receipt` — يبني بايتات ESC/POS من JSON ويطبعها
- `POST /open-drawer` — نبضة فتح الدرج (pin 2)

**بنية محتوى الطباعة:**

```json
{
  "printer": {"connection": "network", "host": "192.168.1.50", "port": 9100, "encoding": "cp864"},
  "content": {
    "lines": [{"text": "فاتورة مبيعات", "align": "center", "bold": true, "double": true}],
    "cut": true,
    "open_drawer": false
  }
}
```

- `align`: `left` / `center` / `right` — و`bold` و`double` (حجم مضاعف) اختياريان
- الترميز الافتراضي `cp864` للعربية؛ والقصّ الكامل `cut` ونبضة الدرج مدعومان
- قناة التوصيل: شبكة TCP على المنفذ `9100`، أو تسلسلية (`COM3` / `/dev/ttyUSB0`) إن وُجدت `pyserial`

**بروكسي الخادم** (يتطلب صلاحية POS):

- `POST /pos/api/hardware/print-receipt` — طباعة عبر الوكيل من الخادم
- `POST /pos/api/hardware/open-drawer` — فتح الدرج
- `GET /pos/api/hardware/status` — حالة الوكيل والطابعة

#### 4.14.3 إعداد الطابعات — `/pos/settings/printers`

**النموذج:** `PosPrinter` — أدوار: `customer` / `kitchen` / `warehouse`، واتصالات: `agent_network` / `agent_serial` / `webusb` / `webserial`.

| الحقل | الوصف |
|---|---|
| الاسم | اسم تعريفي (مثل: طابعة المطبخ) |
| الدور | `customer` إيصال العميل الكامل، `kitchen` تذكرة المطبخ، `warehouse` تذكرة المستودع/التجهيز |
| نوع الاتصال | `agent_network` عبر الوكيل TCP:9100 · `agent_serial` عبر الوكيل تسلسلي · `webusb`/`webserial` مباشرة من متصفح الكاشير |
| المضيف/المنفذ | لطابعات الشبكة (مثل `192.168.1.50:9100`) |
| المنفذ التسلسلي | لطابعات `agent_serial` (مثل `COM3`) |
| الفئات `category_ids` | قائمة معرّفات فئات مفصولة بفواصل؛ **فارغ = كل الفئات** |
| نشط / الترتيب | تعطيل مؤقت وترتيب التوزيع |

**توجيه الفئات (التوزيع الذكي):** طابعة العميل تستلم الإيصال الكامل دائماً؛ طابعات المطبخ/المستودع تستلم فقط الأسطر التي تطابق فئاتها (عبر `covers_category`)، وتُتجاوز الطابعة بلا أسطر مطابقة. مثال مطعم: فئة «مشروبات» ← طابعة البار، فئة «مطبخ» ← طابعة المطبخ، والإيصال الكامل ← طابعة الكاشير.

**إجراءات الصفحة:** إضافة، تبديل النشط، حذف (مع تأكيد).

#### 4.14.4 مسار الطباعة أثناء البيع

1. بعد نجاح checkout (أونلاين أو مؤجل 202) تطلب الشاشة `GET /pos/api/sale/<id>/print-tickets`
2. الخادم يبني تذكرة لكل طابعة نشطة (`build_print_tickets`): كاملة للعميل، ومُرشّحة بالفئات للمطبخ/المستودع
3. المتصفح يوزّع كل تذكرة حسب `connection_type`:
   - `agent_*` ← `POST http://127.0.0.1:8567/print-receipt`
   - `webusb` / `webserial` ← مباشرة عبر `EscposPrinter` (يسأل المتصفح عن الإذن أول مرة)
4. فشل تذكرة واحدة لا يوقف باقي التذاكر — تُرجع الدالة ملخصاً `{ printed, failed[] }` بأسماء الطابعات الفاشلة ولا تتوقف إطلاقاً

**إعادة الطباعة:** أعد فتح الفاتورة واطلب نفس نقطة النهاية — التذاكر تُبنى من جديد من بيانات البيع.

#### 4.14.5 الميزان الإلكتروني (Web Serial)

- زر **⚖️** بجانب حقل البحث في شاشة الكاشير: «توصيل الميزان» / «فصل الميزان» (يُخفى تلقائياً إن لم يدعم المتصفح Web Serial)
- المتطلبات: Chrome/Edge حديث + سياق آمن (HTTPS أو `http://localhost`)
- بعد التوصيل تُقرأ القراءة الحية وتُطبَّق ككمية للصنف الموزون؛ وعند انقطاع الكابل تظهر رسالة «انقطع الاتصال بالميزان» ويتم التنظيف تلقائياً

**الباركود الوزني (بادئة `20`):** للأصناف الموزونة المُعلّبة مسبقاً — صيغة EAN-13:

```
20 XXXXX WWWWW C
│   │      │    └─ رقم التحقق
│   │      └────── الوزن بالغرام (5 خانات)
│   └───────────── رمز الصنف (5 خانات)
└────────────────── بادئة الميزان
```

مثال: `20 00350 01500 6` ← الصنف `00350` بوزن `1.500` كغ. يُحلَّل محلياً في المتصفح (`offline-catalog.js`) ويطابق تحليل الخادم تماماً — فيعمل أونلاين وأوفلاين، وتُملأ الكمية `scale_weight_kg` تلقائياً.

#### 4.14.6 المسح بالكاميرا (BarcodeDetector)

- زر **📷** بجانب حقل البحث: يفتح مربع كاميرا، وجّهه نحو الباركود ليُدرج الصنف فوراً
- يتطلب إذن الكاميرا + متصفحاً يدعم BarcodeDetector (Chrome/Edge) + HTTPS أو localhost
- ماسح USB/بلوتوث التقليدي (وضع لوحة المفاتيح) يعمل دائماً في حقل البحث دون أي إذن — وهو البديل التلقائي

#### 4.14.7 طرفية الدفع (Stripe Terminal)

دفع push-to-terminal: يرسل الخادم مبلغ الفاتورة إلى قارئ البطاقة بدلاً من إدخاله يدوياً.

- `GET /pos/api/terminal/status` — هل مزوّد الطرفية مهيأ؟ (استدعِه أولاً قبل إظهار زر الدفع)
- `POST /pos/api/terminal/connection_token` — رمز اتصال لقارئ Stripe
- `POST /pos/api/terminal/payment_intent` — إنشاء نية دفع بمبلغ الفاتورة

إن لم يكن المزوّد مهيأً يبقى الدفع اليدوي (نقدي/بطاقة يدوية) متاحاً دون تغيير.

#### 4.14.8 شاشة العميل (CFD)

- تعرض للعميل لحظياً: الأسطر، الخصومات، الضريبة، المدفوع، والباقي — عبر SSE، وعند انقطاعه تعمل قناة `BroadcastChannel` احتياطية بين تبويبَي الكاشير والشاشة على نفس الجهاز
- لعدّة شاشات عبر الشبكة: `utils/sse_backplane.py` يدعم Redis اختيارياً لبث الأحداث بين العمال

#### 4.14.9 العمل دون اتصال (Offline Mode)

**لقطة الكتالوج:** `GET /pos/api/catalog/snapshot` يخزّن المنتجات في IndexedDB — البحث بالاسم/الباركود/SKU ومحلل الباركود الوزني يعملان بالكامل دون شبكة.

**طابور العمليات (`pos-sw.js`):** عند انقطاع الشبكة تُصفّ العمليات الحساسة — checkout، الإرجاعات، حذف الأسطر (void-line)، وحركات الدرج — ثم تُعاد تلقائياً:

- إعادة المحاولة بتأخير أسّي: من 15 ثانية حتى 15 دقيقة، بحد أقصى 8 محاولات
- أخطاء العميل 4xx تُحذف من الطابور (لن ينجح تكرارها) باستثناء `408` و`429`
- Background Sync (الوسم `pos-queue-retry`) يستأنف الطابور عند عودة الاتصال

**سلوك الفاتورة المؤجلة (202):** عندما يقبل الخادم البيع للمزامنة اللاحقة تمسح الشاشة السلة، وتعرض تأكيداً واضحاً «الفاتورة في الانتظار»، وتطبع محلياً — لا تظهر كخطأ.

#### 4.14.10 دليل التجربة الميدانية خطوة بخطوة (Field Test)

**أ. التحضير (5 دقائق):**

1. ☐ جهاز كاشير بمتصفح Chrome/Edge حديث، يفتح النظام عبر HTTPS أو `http://localhost`
2. ☐ طابعة حرارية على نفس الشبكة (دوّن IP — مثلاً `192.168.1.50`) أو USB
3. ☐ شغّل الوكيل على الكاشير: `python scripts/hardware_agent/pos_hardware_agent.py`
4. ☐ تحقق: افتح `http://127.0.0.1:8567/status` — يجب أن يرد JSON

**ب. الإقران:**

5. ☐ من `/pos/settings/printers` أضف «طابعة الكاشير»: دور `customer`، اتصال `agent_network`، المضيف/المنفذ الصحيحان
6. ☐ (مطاعم) أضف «طابعة المطبخ»: دور `kitchen` وقيّدها بفئة المطبخ
7. ☐ اضغط **⚖️** واقبل إذن المنفذ التسلسلي — يتحول الزر لحالة «متصل»
8. ☐ اضغط **📷** واقبل إذن الكاميرا وامسح أي باركود منتج

**ج. سيناريو البيع الكامل (أونلاين):**

9. ☐ بع فاتورة بصنف عادي + صنف موزون (باركود بادئة 20 أو وزن حي) + دفع نقدي
10. ☐ تحقق من طباعة إيصال العميل كاملاً وفتح الدرج
11. ☐ (مطاعم) تحقق أن تذكرة المطبخ تحوي أصناف المطبخ فقط
12. ☐ تحقق أن شاشة العميل عرضت الأسطر والضريبة والباقي لحظياً

**د. سيناريو الأوفلاين (أهم اختبار):**

13. ☐ افصل كابل الشبكة عن الكاشير (أو عطّل Wi-Fi)
14. ☐ ابحث عن منتج بالباركود — يجب أن يعمل من اللقطة المحلية
15. ☐ أكمل بيعاً كاملاً — يجب أن يُقبل ويُطبع محلياً مع إشعار «في الانتظار»
16. ☐ أعد الاتصال وانتظر ≤ 15 ثانية — يجب أن تتزامن الفاتورة وتظهر في تقارير المبيعات برقمها
17. ☐ تحقق من عدم تكرار الفاتورة في الخادم (مزامنة واحدة فقط)

**هـ. القبول النهائي:**

18. ☐ أعد طباعة فاتورة سابقة من شاشتها
19. ☐ نفّذ إرجاعاً أونلاين وتأكد من قيد الاسترجاع
20. ☐ أعد تشغيل الوكيل وتأكد أن الطباعة تعود دون لمس الإعدادات

#### 4.14.11 استكشاف الأخطاء وإصلاحها

| العَرَض | السبب الغالب | الحل |
|---|---|---|
| زر الميزان/الكاميرا مختفٍ | المتصفح لا يدعم Web Serial/BarcodeDetector أو الصفحة ليست HTTPS | Chrome/Edge حديث + HTTPS أو localhost |
| «وكيل الأجهزة غير reachable» | الوكيل لا يعمل على الكاشير | شغّله وتحقق من `http://127.0.0.1:8567/status` |
| لا طباعة رغم نجاح البيع | IP/منفذ الطابعة خطأ أو جدار ناري يحجب 9100 | ping للطابعة ثم `telnet <ip> 9100` |
| عربية مشوّهة في الإيصال | ترميز الطابعة | تأكد `cp864` في إعداد الطابعة/الوكيل |
| الدرج لا يفتح | النبضة على pin مختلف | الافتراضي pin 2؛ راجع مواصفات الطابعة |
| تذكرة المطبخ فارغة/مفقودة | فئات الطابعة لا تطابق فئات الأصناف | صحّح `category_ids` أو اتركها فارغة للكل |
| فواتير أوفلاين لا تتزامن | الطابور استنفد 8 محاولات أو Service Worker قديم | حدّث الصفحة بقوة (Ctrl+F5) وأعد البيع |
| «انقطع الاتصال بالميزان» | كابل/منفذ تسلسلي | أعد التوصيل واضغط زر الميزان من جديد |

---

## 5. المبيعات

> **الملف الرئيسي:** `routes/sales.py`

### 5.1 الفاتورة
**نقاط النهاية:**
- `GET /sales` — قائمة الفواتير
- `GET /sales/create` — نموذج إنشاء
- `POST /sales/create` — حفظ فاتورة
- `GET /sales/<id>` — عرض فاتورة
- `GET /sales/<id>/edit` — تعديل
- `POST /sales/<id>/cancel` — إلغاء

**الحالات:**
- `draft` — مسودة
- `active` / `confirmed` — مؤكدة
- `cancelled` — ملغاة

### 5.2 حقول الفاتورة
- `sale_number` — رقم تسلسلي تلقائي
- `customer_id` — العميل
- `seller_id` — البائع
- `warehouse_id` — المستودع
- `total_amount` — الإجمالي
- `paid_amount` — المدفوع
- `balance_due` — المتبقي
- `currency` / `exchange_rate` / `amount_aed` — العملة والتحويل
- `payment_status` — paid, partial, unpaid
- `pos_session_id` — ربط بجلسة POS

### 5.3 أسطر الفاتورة (SaleLine)
- `product_id` — المنتج
- `quantity` — الكمية
- `unit_price` — السعر
- `discount_percent` — نسبة الخصم
- `line_total` — إجمالي السطر
- `cost_price` — تكلفة الوحدة (لحساب COGS)

### 5.4 العمولات
- النظام يحسب عمولة الشريك (Partner) تلقائياً على صافي الربح (الإيرادات بعد VAT ناقص COGS)
- يُرحّل قيد GL للعمولة

### 5.5 الإرجاع
**الملف:** `routes/returns.py` + `services/return_service.py`

**شروط الإرجاع:**
- الفاتورة يجب أن تكون مؤكدة (ليس cancelled أو pending)
- الكمية المُرجعة لا تتجاوز الكمية المباعة ناقص الإرجاعات السابقة
- المنتجات ذات الأرقام التسلسلية: يجب أن تكون الأرقام مرتبطة بالفاتورة وحالتها "sold"

**التأثيرات:**
- استعادة المخزون (return movement)
- عكس COGS (Dr Inventory / Cr COGS)
- عكس الإيرادات (Dr Sales Revenue / Cr Customer)
- استرداد الخصم الترويجي إن وجد
- تحديث رصيد العميل

---

## 6. المخزون والمنتجات

> **الملف الرئيسي:** `routes/products.py`, `routes/warehouse.py`
> **الخدمة:** `services/stock_service.py`

### 6.1 المنتج
**النموذج:** `Product`

| الحقل | الوصف |
|-------|-------|
| `name` / `name_ar` | الاسم |
| `sku` | رقم القطعة (فريد لكل مستأجر) |
| `barcode` | الباركود (فريد لكل مستأجر) |
| `part_number` | رقم الجزء من الشركة المصنعة |
| `cost_price` | التكلفة (يُحدّث تلقائياً من MWAC) |
| `regular_price` | السعر الأساسي |
| `current_stock` | المخزون الكلي (مجموع المستودعات) |
| `min_stock_alert` | حد التنبيه المنخفض |
| `has_serial_number` | يتطلب تتبع تسلسلي |
| `warranty_days` | فترة الضمان |
| `is_returnable` | قابل للإرجاع |
| `extra_fields` | حقول ديناميكية (JSON) |

**ملاحظة:** `sku` و `barcode` فريدان لكل مستأجر (conditional unique index).

### 6.2 فئات المنتجات
**النموذج:** `ProductCategory`
- هرمي (parent_id)
- فريد لكل مستأجر: `(tenant_id, name)`
- لا يمكن حذف فئة تحتوي منتجات

### 6.3 مستويات التسعير (Pricing Tiers)
**النموذج:** `ProductPriceTier`

| المستوى | الكود |
|---------|-------|
| الجملة | wholesale |
| التجزئة | retail |
| التوزيع | distributor |
| المندوب | rep |

### 6.4 المستودعات
**النموذج:** `Warehouse`

| الحقل | الوصف |
|-------|-------|
| `name` / `name_ar` | الاسم |
| `code` | كود فريد |
| `warehouse_type` | physical أو online |
| `parent_id` | مستودع رئيسي (هرمي) |
| `branch_id` | الفرع المرتبط |
| `manager_id` | المسؤول |
| `is_main` | المستودع الافتراضي |
| `allow_negative_inventory` | السماح بالمخزون السالب |

**ملاحظة:** مستودع واحد فقط من نوع online لكل مستأجر.

### 6.5 مخزون المستودعات
**النموذج:** `ProductWarehouseStock`
- فريد: `(tenant_id, product_id, warehouse_id)`
- `quantity` — الكمية الحالية
- `warehouse_barcode` — باركود خاص بالمستودع

### 6.6 حركات المخزون
**النموذج:** `StockMovement`

| النوع | الوصف |
|-------|-------|
| `purchase` | استلام مشتريات |
| `sale` | بيع |
| `adjustment` | تسوية يدوية |
| `return` | إرجاع |
| `damage` | تالف |
| `transfer` | تحويل بين مستودعات |

**الآلية:** كل حركة تمر عبر `StockService.create_movement()`:
1. قفل الصف (SELECT ... FOR UPDATE)
2. التحقق من المخزون السالب
3. تحديث `ProductWarehouseStock`
4. مزامنة `Product.current_stock`
5. بث تنبيه WebSocket

### 6.7 تحويل المخزون
**نقطة النهاية:** `POST /warehouse/transfer`
```json
{
  "product_id": 1,
  "source_id": 2,
  "destination_id": 3,
  "quantity": 10,
  "notes": "..."
}
```

يُنشأ حركتان: خصم من المصدر (+) إضافة للوجهة. صافي الصفر على المخزون الكلي.

### 6.8 تسوية المخزون
**نقاط النهاية:**
- `POST /products/<id>/adjust-stock` — تسوية منتج (add / subtract / set)
- `POST /warehouse/exchange` — تسوية مستودع (IN / OUT)

**التأثير المحاسبي:**
- IN: Dr Inventory Asset / Cr Inventory Adjustment Gain
- OUT: Dr Inventory Adjustment Loss / Cr Inventory Asset

### 6.9 متوسط التكلفة المرجح المتحرك MWAC
**النماذج:** `ProductWarehouseCost` + `ProductCostHistory`

**الحساب:**
```
new_qty   = old_qty + change_qty
new_value = old_value + (change_qty * unit_cost)
new_avg   = new_value / new_qty
```

**التسعير:** unit cost بـ 4 منازل عشرية، COGS بـ 3 منازل.

**السيناريوهات:**
- **استلام:** تحديث MWAC بتكلفة الشراء
- **بيع:** خصم بتكلفة MWAC الحالية
- **مخزون سالب:** استخدام سلسلة fallback: MWAC → SaleLine.cost_price → آخر شراء
- **استلام بعد سالب:** تعديل رجعي (retrospective adjustment) في GL

### 6.10 تسوية المخزون (Reconciliation)
**الخدمة:** `InventoryReconciliationService`

يقارن ثلاثة مصادر:
1. `ProductWarehouseCost` (القيمة التشغيلية)
2. GL Account 1140 (Inventory Asset)
3. `stock_movements` (الحركات الفعلية)

**نقاط النهاية:**
- `GET /reports/inventory-reconciliation` — التقرير

---

## 7. المشتريات

> **الملف الرئيسي:** `routes/purchases.py`
> **الخدمة:** `services/purchase_service.py`

### 7.1 أمر الشراء
**الحقول:**
- `purchase_number` — تلقائي
- `supplier_id` — المورد
- `warehouse_id` — مستودع الاستلام
- `total_amount` — الإجمالي
- `currency` / `exchange_rate` / `amount_aed`
- `freight` / `insurance` / `customs_duty` — تكاليف الشحن والتأمين والجمارك
- `prices_include_vat` — هل الأسعار شاملة VAT؟

### 7.2 استلام المخزون
عند تأكيد أمر الشراء:
1. إضافة مخزون عبر `StockService.add_stock()`
2. تحديث MWAC بتكلفة الشراء
3. ترحيل GL: Dr Inventory / Cr AP

---

## 8. العملاء

> **الملف الرئيسي:** `routes/customers.py`

### 8.1 العميل
**الحقول:**
- `name` — الاسم
- `phone` — الهاتف
- `email` — البريد
- `address` — العنوان
- `balance` — الرصيد (AR)
- `credit_limit` — حد الائتمان
- `customer_type` — regular, vip, wholesale, etc.

### 8.2 الرصيد
- **الصيغة:** Receipts − Sales − Outgoing_Payments_to_customer
- موجب = رصيد دائن (لصالح العميل)
- سالب = مستحق (AR)

### 8.3 نقاط النهاية
- `GET /customers` — القائمة
- `POST /customers/create` — إنشاء
- `GET /customers/<id>` — عرض
- `POST /customers/<id>/edit` — تعديل
- `GET /customers/<id>/statement` — كشف الحساب

---

## 9. الموردين

> **الملف الرئيسي:** `routes/suppliers.py`

### 9.1 المورد
**الحقول:** مشابه للعميل + `tax_number`, `commercial_register`

### 9.2 الرصيد
- **الصيغة:** Purchases − Outgoing_Payments + Incoming_Payments(refunds)
- موجب = نحن مدينون للمورد
- سالب = المورد مدين لنا

### 9.3 نقاط النهاية
- `GET /suppliers` — القائمة
- `POST /suppliers/create` — إنشاء
- `GET /suppliers/<id>/statement` — كشف الحساب

---

## 10. المدفوعات والخزينة

> **الملف الرئيسي:** `routes/payments.py`
> **الخدمة:** `services/payment_service.py`

### 10.1 سند القبض (Receipt)
**الخدمة:** `PaymentService.create_receipt()`

**التأثير:**
- إذا نقد/بطاقة/تحويل: Dr Cash/Bank / Cr AR
- إذا شيك: Dr Cheques Under Collection / Cr AR
- FX Gain/Loss تلقائي إذا اختلف سعر الصرف عن الفاتورة

### 10.2 سند الصرف (Payment)
**الخدمة:** `PaymentService.create_payment()`

**التأثير:**
- إذا نقد/بطاقة: Dr AP / Cr Cash/Bank
- إذا شيك: Dr AP / Cr Deferred Cheques Payable

### 10.3 الدفع المتعدد (Voucher)
**نقاط النهاية:**
- `GET /payments/voucher/create` — نموذج
- `POST /payments/voucher/submit` — حفظ

يدعم incoming و outgoing في نفس النموذج.

### 10.4 تخصيص المدفوعات
- `allocate_to_sales` — توزيع القبض على فواتير غير مسددة
- يُنشأ Payment مرتبط بـ Sale (payment_type="sale_payment")

---

## 11. المصروفات

> **الملف الرئيسي:** `routes/expenses.py`
> **النموذج:** `Expense`, `ExpenseCategory`

### 11.1 فئة المصروفات
- ترتبط بحساب GL (يجب أن يبدأ بـ 5 أو 6)
- فريدة لكل مستأجر: `(tenant_id, name)`

### 11.2 المصروف
**الحقول:**
- `expense_number` — EXP-...
- `description` — الوصف
- `amount` / `currency` / `amount_aed`
- `expense_date`
- `payment_method` — cash, bank_transfer, card, cheque
- `category_id`
- `branch_id`

**إذا كان الدفع بالشيك:**
- يُنشأ Cheque صادر مرتبط بالمصروف
- GL: Dr Expense / Cr Deferred Cheques Payable

### 11.3 التعديل والإلغاء
- التعديل المالي يتطلب: فترة مفتوحة → عكس القيد الأصلي → قيد جديد
- الإلغاء: عكس القيد + تعيين `is_reversed = True`

---

## 12. الشيكات

> **الملف الرئيسي:** `routes/cheques.py`
> **الخدمة:** `services/cheque_service.py`

### 12.1 النموذج
**الحقول:**
- `cheque_type` — incoming (قبض) أو outgoing (صرف)
- `status` — pending, deposited, under_collection, cleared, bounced, cancelled
- `amount` / `currency` / `exchange_rate` / `amount_aed`
- `clearance_exchange_rate` / `actual_amount_aed` / `currency_gain_loss`

### 12.2 دورة الحياة

| المرحلة | الوصف | التأثير المحاسبي |
|---------|-------|------------------|
| **Receive** | استلام شيك من عميل | Dr Cheques Under Collection / Cr AR |
| **Issue** | إصدار شيك لمورد | Dr AP / Cr Deferred Cheques Payable |
| **Deposit** | إيداع الشيك في البنك | لا يوجد تأثير GL |
| **Clear** | تحصيل/صرف الشيك | Dr Bank / Cr Cheques Under Collection (و FX Gain/Loss) |
| **Bounce** | رد الشيك | Dr AR / Cr Cheques Under Collection (استعادة) |
| **Cancel** | إلغاء الشيك | عكس القيد الأصلي |

### 12.3 نقاط النهاية
- `POST /cheques/<id>/deposit` — إيداع
- `POST /cheques/<id>/clear` — تحصيل
- `POST /cheques/<id>/bounce` — رد
- `POST /cheques/<id>/cancel` — إلغاء (admin only)

---

## 13. المحاسبة — دفتر الأستاذ العام

> **الملف الرئيسي:** `routes/ledger.py`, `routes/advanced_ledger.py`, `routes/admin_ledger.py`
> **الخدمات:** `services/gl_service.py`, `services/gl_posting.py`

### 13.1 شجرة الحسابات (COA)
**النموذج:** `GLAccount`

**قاعدة الترميز:**
- 1xxx — الأصول
- 2xxx — الالتزامات
- 3xxx — حقوق الملكية
- 4xxx — الإيرادات
- 5xxx / 6xxx — المصروفات

**الحسابات المحمية:**
`PROTECTED_ACCOUNT_CODES` — لا يمكن حذفها أو تغيير كودها.

### 13.2 القيود (Journal Entries)
**النموذج:** `GLJournalEntry` + `GLJournalLine`

**دورة الحياة:**
```
Draft → Validated → Posted
  └→ Error
Any → Reversed
Any → Cancelled
```

**الحقول:**
- `entry_number` — تلقائي
- `entry_date`
- `reference_type` / `reference_id` — ربط بالمستند المصدر
- `entry_type` — manual, auto, adjustment, closing, reversing
- `currency` / `exchange_rate`
- `total_debit` / `total_credit` — يجب أن يتوازنا ضمن 0.001
- `branch_id` — عزل فرعي

**الأبعاد المالية:**
- `cost_center_id`
- `profit_center_id`
- `partner_id`
- `warehouse_id`

### 13.3 القيد اليدوي
**نقطة النهاية:** `POST /ledger/manual-entry`
**الصلاحية:** `manage_ledger`

الخطوات:
1. إدخال أسطر مع `account_code`, `debit`, `credit`, `description`
2. التحقق من وجود الحسابات وعدم كونها headers
3. تحويل المبالغ إلى العملة الأساسية
4. توازن الأسطر (rounding plug حتى 0.01)
5. إنشاء القيد كـ `draft`
6. التحقق من `validate_entry()`
7. الترحيل `post_entry()`

### 13.4 القيد التلقائي
كل مستند مالي (فاتورة، دفع، مصروف، إرجاع، شيك) يُنشئ قيداً تلقائياً عبر `post_or_fail()`.

### 13.5 عكس القيد
**نقطة النهاية:** `POST /ledger/entry/<id>/reverse`
- يُنشأ قيد جديد بـ `reversing`
- يُبدّل debit ↔ credit
- يُحدّد `reversed_entry_id`

### 13.6 الفترات المالية (GLPeriod)
**الحقول:** `year`, `month`, `is_closed`, `closed_at`, `closed_by`

**الصلاحية:**
- عرض: `view_ledger`
- إغلاق/فتح: `manage_ledger`

**الحماية:** لا يمكن ترحيل قيود في فترة مغلقة.

### 13.7 التقرير المالي الرئيسي
**النقاط:**
- `/ledger/trial-balance` — ميزان المراجعة
- `/ledger/income-statement` — قائمة الدخل
- `/ledger/balance-sheet` — الميزانية العمومية
- `/ledger/cash-flow` — التدفق النقدي
- `/ledger/aging-analysis` — تحليل العمر (AR/AP)

### 13.8 تحليل العمر (Aging)
**الخدمة:** `AgingAnalysisService`

تصنيف الفواتير حسب الفترة:
- حالية (Current)
- 1–30 يوم
- 31–60 يوم
- 61–90 يوم
- +90 يوم

### 13.9 الموازنة (Budget)
**النماذج:** `Budget` + `BudgetLine`
**النقطة:** `/ledger/budget-vs-actual`

يقارن الميزانية بالواقع من GL.

### 13.10 التسوية البنكية
**النماذج:** `BankReconciliation`, `BankReconciliationItem`, `BankStatementLine`

يدعم استيراد كشوف OFX/MT940.

### 13.11 إهلاك الأصول الثابتة
**الخدمة:** `DepreciationService`
**النقطة:** `POST /ledger/run-depreciation`

يدعم الشهري فقط (خلال الفترة المفتوحة).

---

## 14. التقارير

> **الملف الرئيسي:** `routes/reports.py`, `routes/treasury.py`

### 14.1 التقارير المتاحة
| التقرير | الوصف |
|---------|-------|
| مبيعات | حسب الفترة، العميل، البائع، المنتج |
| مشتريات | حسب الفترة، المورد |
| AR Reconciliation | تسوية AR مع دفتر الأستاذ |
| Inventory Reconciliation | تسوية المخزون |
| المستحقات (Receivables) | aging analysis |
| المخزون | حركات وتوازن |
| الأكثر مبيعاً | Top selling products |

### 14.2 الخزينة (Treasury)
- موقف السيولة
- تقرير VAT
- تقرير الشيكات

---

## 15. الموارد البشرية والرواتب

> **الملف الرئيسي:** `routes/payroll.py`, `routes/hr.py`

### 15.1 الموظف
**النموذج:** `Employee`

**الحقول:**
- `name`, `phone`, `email`, `address`
- `basic_salary` — الراتب الأساسي
- `department_id` — القسم
- `job_position_id` — الوظيفة
- `hire_date` — تاريخ التعيين
- `contract_type` — عقد دائم/مؤقت/فريلانس
- `is_active`

### 15.2 الرواتب
**الخدمة:** `PayrollService`

**العملية:**
1. `POST /payroll/process` — تشغيل الرواتب
2. حساب الراتب = basic + allowances − deductions − tax
3. إنشاء `PayrollTransaction`
4. ترحيل GL: Dr Salary Expense / Cr Bank
5. إنشاء قسيمة الراتب (slip)

### 15.3 السلف
**النموذج:** `SalaryAdvance`
- `amount`, `reason`, `status` (pending/approved/rejected/paid)
- `repayment_amount` — مبلغ الاستقطاع الشهري
- يُخصم تلقائياً من الراتب

### 15.4 الحضور
**النموذج:** `Attendance`
- `clock_in` / `clock_out`
- `status` — present, absent, late, early_leave

### 15.5 الإجازات
**النموذج:** `LeaveRequest`
- `leave_type_id` — نوع الإجازة (سنوية، مرضية، ...)
- `start_date` / `end_date`
- `status` — pending/approved/rejected
- `days` — عدد الأيام

---

## 16. إدارة علاقات العملاء CRM

> **الملف الرئيسي:** `routes/crm.py`
> **الخدمة:** `services/crm_lead_service.py`

### 16.1 العملاء المحتملون (Leads)
**النموذج:** `CRMLead`

| الحقل | الوصف |
|-------|-------|
| `name` | الاسم |
| `email` / `phone` | التواصل |
| `company` | الشركة |
| `source` | المصدر (website, referral, social, etc.) |
| `stage_id` — المرحلة | pipeline stage |
| `team_id` — الفريق | assigned team |
| `assigned_to_id` | المسؤول |
| `estimated_value` — القيمة المتوقعة | |
| `probability` — الاحتمالية | % |
| `expected_close_date` | |

### 16.2 مراحل الأنابيب (Pipeline)
**النموذج:** `CRMStage`
- `name`, `color`, `sort_order`
- ربط بـ `tenant_id`

### 16.3 الأنشطة
**النموذج:** `CRMActivity`
- `activity_type` — call, meeting, email, note, task
- `due_date`
- `completed_at`

---

## 17. المشاريع

> **الملف الرئيسي:** `routes/projects.py`
> **الخدمة:** `services/project_service.py`

### 17.1 المشروع
**النموذج:** `Project`

| الحقل | الوصف |
|-------|-------|
| `name` | اسم المشروع |
| `description` | التفاصيل |
| `status` — not_started, in_progress, on_hold, completed, cancelled |
| `priority` — low, medium, high, urgent |
| `start_date` / `end_date` | |
| `budget` | الميزانية |
| `manager_id` | المدير |

### 17.2 المهام
**النموذج:** `Task`
- `title`, `description`, `status`
- `priority`, `due_date`
- `project_id`, `assigned_to_id`
- `parent_id` — مهمة فرعية

### 17.3 ساعات العمل
**النموذج:** `Timesheet`
- `task_id`, `user_id`
- `hours`, `date`, `description`

### 17.4 أعضاء المشروع
**النموذج:** `ProjectMember`
- `project_id`, `user_id`, `role`

---

## 18. التذاكر والدعم الفني

> **الملف الرئيسي:** `routes/tickets.py`
> **الخدمة:** `services/ticket_service.py`

### 18.1 التذكرة
**النموذج:** `Ticket`

| الحقل | الوصف |
|-------|-------|
| `ticket_number` — رقم تسلسلي | |
| `subject` | الموضوع |
| `description` | التفاصيل |
| `category_id` — الفئة | |
| `priority_id` — الأولوية | low, medium, high, urgent |
| `status` — open, in_progress, waiting, resolved, closed |
| `assigned_to_id` | المسؤول |
| `customer_id` | العميل (اختياري) |
| `due_date` — SLA | |

### 18.2 التعليقات
**النموذج:** `TicketComment`
- `ticket_id`, `user_id`, `content`
- `is_internal` — تعليق داخلي (غير مرئي للعميل)

---

## 19. التسويق والبريد الإلكتروني

> **الملف الرئيسي:** `routes/email_marketing.py`
> **الخدمة:** `services/email_marketing_service.py`

### 19.1 الحملات
**النموذج:** `EmailCampaign`

| الحقل | الوصف |
|-------|-------|
| `name` | اسم الحملة |
| `subject` | موضوع الرسالة |
| `body` | المحتوى |
| `status` — draft, scheduled, sending, sent, paused |
| `scheduled_at` | موعد الإرسال |
| `list_id` | القائمة المستهدفة |
| `template_id` | القالب |

### 19.2 القوائم والمشتركون
**النماذج:** `EmailList`, `EmailSubscriber`
- `EmailList`: `name`, `description`
- `EmailSubscriber`: `email`, `name`, `list_id`, `status` (subscribed/unsubscribed/bounced)

### 19.3 القوالب
**النموذج:** `EmailTemplate`
- `name`, `subject`, `body` (HTML)
- متغيرات ديناميكية: `{{name}}`, `{{company}}`, etc.

---

## 20. المتجر الإلكتروني

> **الملف الرئيسي:** `routes/shop.py` (public), `routes/store.py` (admin)

### 20.1 الواجهة العامة (Shop)
**البادئة:** `/s/<store_slug>/`

**الصفحات:**
- `/s/<slug>/` — الصفحة الرئيسية (catalog)
- `/s/<slug>/product/<id>` — صفحة المنتج
- `/s/<slug>/cart` — العربة
- `/s/<slug>/checkout` — الدفع
- `/s/<slug>/account` — حساب العميل
- `/s/<slug>/orders` — الطلبات
- `/s/<slug>/wishlist` — المفضلة

### 20.2 إدارة المتجر (Store Admin)
**البادئة:** `/store/`
**الصلاحية:** `manage_store`

**الأقسام:**
- Catalog — إدارة المنتجات المعروضة
- Orders — طلبات المتجر
- Customers — عملاء المتجر
- Coupons — كوبونات الخصم
- Settings — إعدادات المتجر

### 20.3 الكوبونات
**النموذج:** `StoreCoupon`
- `code` — رمز الكوبون
- `discount_type` — percentage أو fixed
- `discount_value` — قيمة الخصم
- `min_order_amount` — الحد الأدنى
- `max_uses` / `used_count`
- `valid_from` / `valid_until`
- `applies_to` — all, category, product

### 20.4 طرق الدفع
**النموذج:** `StorePaymentMethod`
- `method` — cash_on_delivery, card, bank_transfer, nowpayments
- `is_enabled`
- `display_name`, `instructions`

### 20.5 طلبات المتجر
**النموذج:** (Sale مع `source="online_store"`)

**دورة الحياة:**
```
pending → confirmed → processing → shipped → delivered
   └→ cancelled
```

**التأكيد:** `StoreOrderService.confirm_order()` — يخصم المخزون ويُنشئ فاتورة، ويُسجّل عمولة المنصة (انظر 20.7).

### 20.6 عملة عرض الأسعار (Display Currency)
- من **Settings** في إدارة المتجر يمكن ضبط حقل **عملة عرض الأسعار** (`display_currency`) — مثلاً `USD` — لتظهر كل أسعار الواجهة بها.
- عند ترك الحقل فارغًا تُستخدم العملة الافتراضية للمنشأة (`default_currency`) ثم العملة الأساسية.
- السعر المعروض **موحّد** في كل الصفحات: الكتالوج، صفحة المنتج، العربة، إتمام الشراء، العرض السريع، المفضلة، ونتائج البحث — عبر محرك تسعير مركزي (`StorePricingService`).
- التحويل يعتمد سعر الصرف المباشر ثم المخزّن؛ إن تعذّر الاثنان يُسجَّل تحذير ولا يُستخدم سعر وهمي (=1).

### 20.7 عمولة منصة أزاد
- تُسجَّل عمولة المنصة تلقائيًا على **كل طلبات المتجر المؤكَّدة** (`source="online_store"`) أيًا كانت قناة الدفع: كاش عند الاستلام، تحويل بنكي، محفظة إلكترونية، أو دفع إلكتروني.
- القنوات غير الإلكترونية خاضعة للإعداد المركزي `azad_platform_fee_include_offline` في إعدادات النظام (مالك المنصة)؛ الدفع الإلكتروني مُتتبَّع دائمًا.
- التسجيل **idempotent** — إعادة تأكيد الطلب أو تكرار الاستدعاء لا تُنشئ عمولة مزدوجة — مع قيد GL متوازن لكل عمولة.
- **لوحة تحكم المتجر** (`/store/admin`) تعرض:
  - إجمالي العمولات المتراكمة بانتظار التسوية.
  - حالة التسوية بعدّادات: متراكمة / مسوّاة / مدفوعة.
  - تنبيه المخزون المنخفض في مستودع الأونلاين (وفق حد التنبيه في الإعدادات).

---

## 21. المساعد الذكي AI

> **الملف الرئيسي:** `routes/ai_routes/assistant.py`
> **الخدمة:** `services/ai_service.py`

### 21.1 الوصول
**الرابط:** `/ai/assistant`
**الصلاحية:** `view_reports`

### 21.2 مستويات الوصول
| المستوى | الصلاحيات |
|---------|-----------|
| `basic` | محادثة + إحصائيات بسيطة |
| `advanced` | + تحليلات وتنبؤات |
| `execute` | + تنفيذ عمليات على قاعدة البيانات |

### 21.3 الأوامر المدعومة (ActionDispatcher)
| الأمر | الصلاحية |
|-------|----------|
| إنشاء عميل | `manage_customers` |
| إنشاء منتج | `manage_products` |
| إنشاء فاتورة | `manage_sales` |
| استلام دفعة | `manage_payments` |
| تسجيل مصروف | `manage_expenses` |
| إنشاء مورد | `manage_suppliers` |
| إنشاء موظف | `manage_employees` |
| إنشاء أمر شراء | `manage_purchases` |
| إنشاء مستخدم | `manage_users` (owner only) |
| ملخص المبيعات | `view_reports` |
| ملخص الأرباح | `view_reports` |
| فحص المخزون | `manage_warehouse` |

**الصيغة:**
- `عميل: الاسم, الهاتف, العنوان`
- `فاتورة: العميل, المنتج, الكمية`
- `استلام: العميل, المبلغ, الطريقة`
- `مصروف: الوصف, المبلغ`

### 21.4 التأكيد (Confirmation Gate)
جميع العمليات التدميرية تتطلب `confirmed=true` صريحاً قبل التنفيذ.

### 21.5 الأمان
- فحص الحقن (prompt injection regex)
- فحص الحساسية (كلمات مرور، مفاتيح)
- تسجيل audit لكل عملية

---

## 22. الإعدادات والإدارة

### 22.1 إعدادات المستأجر (Tenant)
**النموذج:** `Tenant`

**الحقول:**
- `name` / `name_ar` / `name_en`
- `slug` — المعرف الفريد
- `business_type` — نوع النشاط
- `base_currency` — العملة الأساسية
- `default_currency` / `default_language` / `timezone`
- `subscription_plan` — basic, pro, enterprise
- `enable_pos`, `enable_store`, `enable_multi_warehouse`, `enable_multi_currency`, `enable_gl`, `enable_ai`, `enable_reports`, etc.
- `prices_include_vat`
- `brand_color_primary` / `brand_color_secondary`

### 22.2 حدود الموارد (Resource Limits)
| المورد | الحد |
|--------|------|
| max_users | عدد المستخدمين |
| max_products | المنتجات |
| max_customers | العملاء |
| max_suppliers | الموردين |
| max_branches | الفروع |
| max_warehouses | المستودعات |
| max_storage_mb | التخزين |
| max_invoices_per_month | الفواتير/شهر |
| max_sales_per_month | المبيعات/شهر |

### 22.3 الإعدادات العامة
**النموذج:** `SystemSettings`
- `enable_pos`, `enable_store`
- `default_tax_rate`
- `vat_country`
- `date_format`, `time_format`
- `fiscal_year_start`

### 22.4 إعدادات الفاتورة
**النموذج:** `InvoiceSettings`
- `prefix` — بادئة رقم الفاتورة
- `starting_number`
- `terms_and_conditions`
- `footer_text`

---

## 23. الصلاحيات والأدوار

### 23.1 أنواع الصلاحيات (32 نوع)

| الكود | الوصف |
|-------|-------|
| `manage_sales` | المبيعات وPOS |
| `manage_purchases` | المشتريات |
| `manage_products` | المنتجات والمخزون |
| `view_products` | عرض المنتجات فقط |
| `manage_customers` | العملاء |
| `manage_suppliers` | الموردين |
| `manage_payments` | المدفوعات والشيكات |
| `manage_expenses` | المصروفات |
| `view_reports` | التقارير والخزينة |
| `manage_warehouse` | المستودعات |
| `manage_store` | إدارة المتجر |
| `view_ledger` | دفتر الأستاذ (قراءة) |
| `manage_ledger` | دفتر الأستاذ (كتابة) |
| `admin` | إدارة عامة |
| `manage_users` | المستخدمين |
| `manage_backups` | النسخ الاحتياطي |
| `manage_payroll` | الرواتب |
| `crm.view` | CRM (قراءة) |
| `crm.manage` | CRM (كتابة) |
| `support.view` | التذاكر (قراءة) |
| `support.manage` | التذاكر (كتابة) |
| `project.view` | المشاريع (قراءة) |
| `project.manage` | المشاريع (كتابة) |
| `hr.view` | الموارد البشرية (قراءة) |
| `hr.manage` | الموارد البشرية (كتابة) |
| `marketing.manage` | التسويق |
| `printing.print` | الطباعة |
| `printing.settings` | إعدادات الطباعة |
| `view_kds` | شاشة المطبخ |
| `override_sale_price` | تعديل السعر |
| `pos_void_line` | حذف سطر POS |
| `pos_discount_override` | خصم يدوي POS |
| `pos_no_sale_drawer` | فتح الدرج |
| `pos_pay_in_out` | إيداع/صرف |
| `pos_authorize_override` | تفويض مشرف |
| `pos_view_expected` | رؤية الرصيد المتوقع |
| `pos_return` | إرجاع POS |

### 23.2 المستويات الهرمية للأدوار
- **Owner** — كل الصلاحيات + الوصول للوحة المالك
- **Super Admin** — كل الصلاحيات ما عدا إعدادات المنصة
- **Manager** — إدارة العمليات
- **Accountant** — المحاسبة والتقارير
- **Seller** — المبيعات
- **Cashier** — نقاط البيع
- **Warehouse Manager** — المخزون
- **Branch Manager** — إدارة فرع

---

## 24. الفروع والمتاجر المتعددة

### 24.1 الفرع
**النموذج:** `Branch`

| الحقل | الوصف |
|-------|-------|
| `name` | اسم الفرع |
| `code` | كود فريد |
| `is_main` | الفرع الرئيسي |
| `address` / `city` / `country` | العنوان |
| `phone` | الهاتف |

### 24.2 العزل
- كل مستخدم يُربط بـ `branch_id`
- المستخدمون العامون (owner, super_admin, developer) يمكنهم التبديل بين "جميع الفروع"
- المستخدمون المربوطون بفرع محدد مقيدون بفرعهم

### 24.3 رؤية المخزون
- `get_accessible_warehouses(user)` — يعيد المستودعات المسموح بها
- `get_branch_stock_map()` — يعيد إجمالي المخزون لكل منتج في الفروع المسموح بها
- `get_visible_products_query()` — يُظهر فقط المنتجات التي لها حركات مخزون في المستودعات المسموح بها

---

## 25. API والتكاملات الخارجية

### 25.1 REST API
| النقطة | الوصف |
|--------|-------|
| `/api/health` | حالة النظام |
| `/api/version` | إصدار النظام |
| `/api/v2/sales` | المبيعات (paginated) |
| `/api/v2/customers` | العملاء |
| `/api/v2/products` | البحث في المنتجات |
| `/api/v2/stock/sync` | مزامنة مخزون خارجية |
| `/api/analytics/...` | التحليلات |

### 25.2 GraphQL
**النقطة:** `/graphql`
- Query depth limit: 8 levels
- Query length limit: 8000 chars
- Mutations محظورة في الإنتاج
- Rate limit: 60/minute

### 25.3 WebSocket
**الأحداث:**
- `sale_created` — فاتورة جديدة
- `payment_received` — دفعة مستلمة
- `stock_alert` — تنبيه مخزون
- `notification` — إشعار مستهدف

### 25.4 Webhooks
| Webhook | الوصف |
|---------|-------|
| `/billing-webhook/stripe` | دفعات Stripe |
| `/billing-webhook/generic` | Webhook عام |
| `/api/v2/stock/sync` | مزامنة مخزون POS خارجي |

### 25.5 تكاملات الدفع
- **Stripe** — بطاقات ائتمان
- **NOWPayments** — دفع عملات مشفرة

### 25.6 مفاتيح API
**النموذج:** `APIKey`
- `key` / `secret` / `service`
- `scope` — read أو write
- `tenant_id` — ربط بالمستأجر

---

## 26. الأمان والتدقيق

### 26.1 عزل المستأجرين (4 طبقات)

**الطبقة 1:** ORM Auto-Scoping
- `do_orm_execute` event listener — يضيف `WHERE tenant_id = X` تلقائياً لكل SELECT
- `before_flush` event — يتحقق من INSERT/UPDATE/DELETE
- `Session.get()` patched — يرجع None إذا كان tenant_id غير مطابق

**الطبقة 2:** Query Helpers
- `tenant_query(model)` — فلترة حسب المستأجر
- `tenant_get(model, pk)` — جلب + تحقق
- `assert_tenant_record(record)` — تأكيد الملكية

**الطبقة 3:** Request Level
- `before_request` — تحديد `g.active_tenant_id`
- فحص حالة الاشتراك (active/suspended/expired)

**الطبقة 4:** Blueprint Guards
- `@permission_required`
- `@admin_required`
- `@owner_required`
- `@require_subscription_feature`
- `@enforce_resource_limit`

### 26.2 سجل التدقيق
**النماذج:**
- `AuditLog` — سجل العمليات
- `ErrorAuditLog` — سجل الأخطاء
- `JournalEntryAudit` — تدقيق القيود

**الحقول:**
- `action` (create/update/delete)
- `table_name`, `record_id`
- `changes` (JSON)
- `user_id`, `tenant_id`
- `timestamp`

### 26.3 الأمان
- CSRF protection (Flask-WTF)
- Rate limiting (Flask-Limiter)
- Account lockout (5 محاولات)
- Session rotation on login
- Content Security Policy (CSP)
- SQL injection prevention (ORM + parameterized queries)
- XSS prevention (Jinja auto-escaping)

### 26.4 النسخ الاحتياطي
**الخدمة:** `BackupService`
- نسخ PostgreSQL كاملة
- نسخ scoped (tenant/branch/store) بصيغة JSONL
- إمكانية الاستعادة مع remap للـ IDs

---

## ملحق: جداول قاعدة البيانات الرئيسية

### المستخدمون والأمن
`users`, `roles`, `permissions`, `login_history`, `security_alerts`, `api_keys`

### المستأجر والفروع
`tenants`, `branches`, `tenant_stores`, `system_settings`, `integration_settings`, `invoice_settings`, `document_sequences`, `fiscal_positions`

### العملاء والموردين
`customers`, `suppliers`, `shop_customer_accounts`

### المنتجات والمخزون
`products`, `product_categories`, `product_partners`, `product_serials`, `product_images`, `product_price_tiers`
`warehouses`, `stock_movements`, `product_warehouse_stock`, `product_warehouse_costs`, `product_cost_history`, `exchange_rate_records`, `sync_batches`, `idempotency_keys`

### المبيعات وPOS
`sales`, `sale_lines`, `product_returns`, `product_return_lines`
`pos_sessions`, `pos_shifts`, `pos_floors`, `pos_tables`, `pos_table_orders`, `pos_kds_orders`, `pos_order_types`, `pos_override_tokens`, `pos_carts`, `pos_cash_movements`

### المشتريات
`purchases`, `purchase_lines`, `purchase_returns`, `purchase_return_lines`

### المدفوعات
`payments`, `receipts`, `cheques`, `card_vaults`, `card_payments`, `cash_boxes`, `payment_vaults`, `payment_transactions`, `payment_logs`, `donations`, `packages`, `package_purchases`

### المحاسبة
`gl_accounts`, `gl_journal_entries`, `gl_journal_lines`, `gl_periods`, `gl_account_mappings`, `bank_reconciliations`, `bank_reconciliation_items`, `bank_statement_lines`, `budgets`, `budget_lines`, `cost_centers`, `profit_centers`, `fixed_assets`, `depreciation_schedules`, `customs_taxes`, `advanced_expenses`, `tax_calculation_rules`, `journal_entry_audits`

### المصروفات
`expenses`, `expense_categories`

### الشراكة
`partners`, `partner_commission_entries`, `partner_profit_distributions`, `partner_transactions`

### CRM والدعم
`crm_stages`, `crm_teams`, `crm_team_members`, `crm_leads`, `crm_activities`, `ticket_categories`, `ticket_priorities`, `tickets`, `ticket_comments`

### المشاريع
`projects`, `task_stages`, `tasks`, `timesheets`, `project_members`

### الموارد البشرية
`employees`, `salary_advances`, `payroll_transactions`, `payroll_settings`, `departments`, `job_positions`, `hr_contracts`, `attendances`, `leave_types`, `leave_requests`

### التسويق
`campaigns`, `sale_campaigns`, `email_lists`, `email_subscribers`, `email_templates`, `email_campaigns`, `campaign_logs`

### المتجر
`shop_wishlists`, `shop_reviews`, `shop_abandoned_carts`, `shop_saved_payments`, `shop_product_variants`, `shop_stock_alerts`, `shop_newsletters`, `shop_loyalties`, `shop_loyalty_transactions`, `store_coupons`, `store_payment_methods`

### الشحن والضمان
`shipments`, `warranty_claims`

### التدقيق والمستندات
`document_snapshots`, `document_verifications`, `print_histories`, `audit_logs`, `error_audit_logs`, `archived_records`

### المنصة
`azad_platform_fees`, `azad_subscription_fees`


