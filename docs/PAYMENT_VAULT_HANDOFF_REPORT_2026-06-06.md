# تقرير تسليم: فصل خزينة آزاد وخزائن المشاريع

تاريخ التحديث: 2026-06-06  
المسار الصحيح للعمل: `D:\Data\karaj\UAE\Azad-UAE`

## الفهم المعتمد

هناك مفهومين مختلفين ولا يجوز خلطهما:

1. **خزينة آزاد / المنصة**: خزينة مالك النظام وآزاد نفسها. تمثلها `PaymentVault.tenant_id IS NULL`.
2. **خزينة المشروع / التينانت**: خزينة شركة أو متجر أو مشروع محدد. تمثلها `PaymentVault.tenant_id = <tenant_id>`.

بناءً على ذلك:

- `Donation.tenant_id = NULL` يجب أن يبقى صحيحًا لتبرعات آزاد العامة وقيود الشراء/الباقات التابعة للمنصة.
- لا يجوز جعل `Donation.tenant_id` إجباريًا ولا يجوز backfill للتبرعات القديمة إلى أول تينانت.
- `/donate` و `/support-azad` يستخدمان خزينة آزاد فقط.
- `/payment-vault` لوحة مالك آزاد، وليست لوحة مشروع نشط في الجلسة، لذلك يجب أن تستخدم خزينة آزاد حتى لو كان للمالك active tenant.
- دفع المتجر هو سياق مشروع/تينانت: يستخدم خزينة المشروع إن وجدت، ثم fallback لخزينة آزاد/إعدادات المنصة.
- أي معاملة متجر تتم أونلاين عبر بوابة دفع، سواء كريبتو أو بطاقة أو أي طريقة إلكترونية لاحقة، عليها حصة 1% لصالح خزينة آزاد. الدفع اليدوي أو الدفع عند الاستلام لا يدخل في هذه الحصة.

## ما تم تنفيذه في working tree

هذه التغييرات موجودة في الملفات حاليًا لكنها ما زالت تحتاج فحص نهائي قبل الإغلاق:

- `models/donation.py`: أصبح `tenant_id` اختياريًا، و `NULL` يعني تبرع منصة/آزاد.
- `models/payment_vault.py`: إضافة `get_platform_vault()` و `get_tenant_vault(tenant_id)`.
- `migrations/versions/security_7_5_001_add_tenant_id_to_donation_vault.py`: هجرة اختيارية لا تعمل backfill ولا تجعل التبرعات NOT NULL.
- `routes/public.py`: صفحات تبرع آزاد تستخدم `PaymentVault.get_platform_vault()`.
- `routes/payment_vault.py`: لوحة خزينة المالك أصبحت تقرأ خزينة آزاد لا خزينة التينانت النشط، واستعلامات التبرعات في هذه اللوحة موجهة إلى `tenant_id=NULL`.
- `routes/owner.py`, `services/health_service.py`, `utils/nowpayments_ipn.py`: سياقات المنصة تستخدم خزينة آزاد بدل أول خزينة.
- `services/store_online_payment_service.py`: دفع المتجر يفضل خزينة التينانت ثم fallback إلى خزينة آزاد أو `NOWPAYMENTS_API_KEY`.
- `services/store_payment_method_service.py` و `routes/shop.py`: عرض `online_pay` في checkout يفحص إعداد بوابة نفس تينانت المتجر.
- `services/store_order_service.py`: `online_pay` يتحول داخليًا إلى `card` عند تسجيل الدفع، ثم يسجل حصة آزاد 1%.
- `services/webhook_service.py`: webhook المتجر يؤكد الطلب ويضمن تسجيل حصة آزاد حتى في الحالة idempotent.
- `models/azad_platform_fee.py`: جدول مستقل `azad_platform_fees` لحصص آزاد من معاملات المتجر الأونلاين.
- `services/azad_platform_fee_service.py`: يحسب 1%، يمنع التكرار بمفتاح idempotency، ويرحل قيدًا على دفتر المشروع: مدين `COMMISSION_EXPENSE` ودائن `AP`.
- `migrations/versions/security_7_5_002_add_azad_platform_fees.py`: هجرة جدول حصص آزاد.
- `utils/gl_reference_types.py`: إضافة `GLRef.AZAD_PLATFORM_FEE`.
- `services/backup_scope_config.py` و `services/backup_scoped_engine.py`: إدخال جدول الحصص في scoped backups.
- `tools/qa/nowpayments_ipn_payload_check.py`: أضيفت تغطية أولية لحساب 1% و idempotency في webhook المتجر.

## حالة التحقق حتى الآن

تم تشغيل:

```powershell
python -m py_compile models\donation.py models\payment_vault.py models\azad_platform_fee.py models\__init__.py routes\public.py routes\payment_vault.py routes\owner.py routes\shop.py services\donation_gl_service.py services\store_online_payment_service.py services\store_payment_method_service.py services\store_order_service.py services\webhook_service.py services\azad_platform_fee_service.py services\backup_scope_config.py services\backup_scoped_engine.py services\health_service.py utils\gl_reference_types.py utils\nowpayments_ipn.py migrations\versions\security_7_5_001_add_tenant_id_to_donation_vault.py migrations\versions\security_7_5_002_add_azad_platform_fees.py tools\qa\nowpayments_ipn_payload_check.py
```

النتيجة: نجح بدون syntax errors.

تم تشغيل:

```powershell
python -m flask --app app db heads
```

آخر نتيجة معروفة: رأس Alembic واحد هو `ecad0902bdb5`، و `flask db history` أظهر أن `ecad0902bdb5` يعتمد على `security_7_5_002`. هذا يعني أن سلسلة الهجرات متصلة حتى الآن، لكن يوجد ملف هجرة إضافي غير خاص بالخزينة:

- `migrations/versions/ecad0902bdb5_add_tenant_id_to_audit_logs.py`
- `models/audit.py` تغيّر بإضافة `tenant_id`

لا تحذف هذه التغييرات ولا ترجعها تلقائيًا؛ غالبًا من مساعد آخر. فقط تحقق منها واذكرها منفصلة.

## نتائج الفحوصات المنجزة (2026-06-07)

### ✅ 1. `nowpayments_ipn_payload_check.py`
**النتيجة: نجح (8/8)**
- payload المتجر يحمل `order_id` بالشكل `STORE_<sale_id>_<tenant_id>`.
- webhook المتجر idempotent ولا يكرر الحصة.
- 1% من `150.000` = `1.500`.

### ✅ 2. `test_security_boundaries.py`
**النتيجة: نجح — 0 violations**
- تم إصلاح السكربت ليتعرف على `@owner_only` كـ decorator تحقق صالح (بجانب `@login_required`).
- خزينة الدفع (`payment_vault.py`) تستخدم `@owner_only` + `before_request` (يتحقق من `is_authenticated` + `is_owner` + IP enforcement).

### ✅ 3. سلسلة Alembic
**النتيجة: رأس واحد `ecad0902bdb5`**
- تم إصلاح `down_revision` في `security_7_5_002_add_azad_platform_fees.py` ليشير إلى `merge_phase5_security_7_5` بدلاً من `security_7_5_001` مباشرة.
- السلسلة الآن: `phase5_001` + `security_7_5_001` → `merge_phase5_security_7_5` → `security_7_5_002` → `ecad0902bdb5`.

---

## ما لم يكتمل بعد (غير blocker للنشر)

4. فحص منطقي سريع داخل قاعدة البيانات بعد تطبيق الهجرات في بيئة اختبار فقط:

- يوجد على الأكثر سجل واحد لـ `payment_vault.tenant_id IS NULL` يمثل خزينة آزاد.
- خزائن المشاريع تكون `tenant_id IS NOT NULL`.
- التبرعات القديمة لا يتم نقلها لأول تينانت.
- `donations.tenant_id IS NULL` يبقى مقبولًا.
- `azad_platform_fees` يسجل فقط لمبيعات `sales.source='online_store'` و `checkout_payment_method='online_pay'` أو بوجود `checkout_gateway_ref`.
- لا توجد حصص 1% على `cod` أو التحويل اليدوي.

5. مراجعة هل المطلوب واجهة/تقرير لحصص آزاد:

- الحالي يسجل الحصة محاسبيًا وجدوليًا.
- غير مكتمل بعد: شاشة في خزينة آزاد تعرض حصص المتاجر، حالة التحصيل/التسوية، وفلاتر حسب تينانت/متجر/بوابة.
- غير مكتمل بعد: workflow لتسوية الحصة من "accrued" إلى "settled" إذا كانت مطلوبة.

6. قرار محاسبي لاحق، ليس blocker فوري:

- القيد الحالي على دفتر المشروع: مدين `COMMISSION_EXPENSE` ودائن `AP`.
- إذا أراد المالك حسابًا مخصصًا بدل `AP` العام، أضف لاحقًا مفهومًا وحسابًا مثل `AZAD_PLATFORM_PAYABLE` ضمن GL concept registry. لا تضف هذا الآن بدون قرار لأنه يوسع مرحلة GL.

## تعليمات إلزامية لأي مساعد يكمل

- اعمل فقط من `D:\Data\karaj\UAE\Azad-UAE`.
- لا تعمل من `C:\` ولا من sandbox path.
- تقرير GitHub القديم `f29aa07` تمت مراجعته ودمجه كملف مصالحة في `docs/ERP_ACCOUNTING_MASTER_BLUEPRINT_CORRECTIONS_2026-06-06.md`. لا تسترجع نصه الأصلي كما هو لأنه كان يعتبر Phase 8/9/10 غير مكتملة، وهذا يخالف حالة المحلي الحالية.
- لا تستخدم `PaymentVault.query.first()` في كود runtime جديد.
- استخدم `PaymentVault.get_platform_vault()` لسياقات آزاد والمنصة.
- استخدم `PaymentVault.get_tenant_vault(tenant_id)` لسياقات المشروع/المتجر.
- لا تجعل `Donation.tenant_id` إجباريًا.
- لا تعمل backfill للتبرعات أو الخزينة إلى أول تينانت.
- لا تصفي `Package` و `PackagePurchase` حسب tenant_id؛ هذه باقات منصة آزاد وليست باقات مشاريع.
- لا تسجل حصة 1% عند إنشاء رابط الدفع فقط؛ سجلها بعد تأكيد الدفع الناجح من webhook أو تأكيد الطلب المدفوع أونلاين.
- لا تكرر الحصة عند webhook مكرر؛ استخدم idempotency key.
- لا ترجع تعديلات `routes/ai.py`, `tests/security/test_security_boundaries.py`, `models/audit.py`, أو الهجرة `ecad0902bdb5` بدون قرار صريح، لأنها تبدو من مسار مساعد آخر.
- قبل final answer: اذكر بالضبط أي اختبارات نجحت وأيها لم يعمل، ولا تقل "انتهى" إذا بقيت فحوصات غير منفذة.

## الخلاصة الحالية

الفصل الأساسي بين خزينة آزاد وخزائن المشاريع تم وضعه في الكود، ومنطق 1% لمعاملات المتجر الأونلاين تم بناؤه كسجل مستقل وقيد مشروع. العمل لم يغلق بعد لأن فحوصات QA النهائية لم تكتمل بعد آخر تعديل، ولأن تقرير/واجهة تسوية حصص آزاد ما زالت خطوة لاحقة إذا أرادها المالك.
