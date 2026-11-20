# المراجعة المحاسبية الشاملة — 2026-11-20

**الدور:** محاسب الشركة العام · **النطاق:** كل مسارات المال ومصادره في النظام
**المنهج:** مسح ثابت لكل `routes/` و`services/` و`models/` + تحقق عملي على قاعدة بذور نظيفة + بوابات CI المحلية.

---

## 1. ما تبيّن سليماً (لا إجراء)

- دفتر اليومية متوازن فعلياً: `SUM(debit) - SUM(credit) = 0.000` لكل تينانت على 22 تينانت (مثال: tenant 1 → 336 سطر، 17,688.000 مدين/دائن).
- `scripts/ops/reconcile_historical_balances.py` → `total_discrepancies: 0`.
- كل أعمدة المال `Numeric(15,3)`/`Numeric(18,3)` — لا يوجد `Float` مالي.
- لا `request.get_json()` بدون `silent=True`، ولا `commit()`/`rollback()` مباشر في `routes/` أو `models/`.
- قفل `SELECT FOR UPDATE` موجود على تسلسلات المستندات والمخزون وجلسات POS.
- مفاهيم GL الـ 88 مسجّلة ومطابقة بين `GL_CONCEPT_CODES` و`GL_CONCEPT_REGISTRY` وقاعدة البيانات.
- قيود POS (checkout، إرجاع، حركات الدرج) متوازنة ومُختمة بالفرع الصحيح.

---

## 2. عيوب تم إصلاحها وتحقق منها

| # | الخطورة | العيب | الإصلاح | التحقق |
|---|---|---|---|---|
| 1 | **P0** | `routes/assets.py`: إنشاء/تعديل/استهلاك/تصرف في الأصول الثابتة **لا يُحفظ إطلاقاً** — الخدمة `flush` فقط ولا يوجد `commit` في المسار ولا في `app/factory.py` | أضيفت `atomic_transaction`Around الأربع عمليات | قبل الإصلاح: `PERSISTED []` رغم `id=2`؛ بعده: `PERSISTED [(3, 'Audit Test Asset Fixed')]` |
| 2 | **P1** | `exchange_rate_service._save_rate_record` يستدعي `atomic_transaction` داخلياً، فيُنهي معاملة البيع/الشراء قبل اكتمالها → أرقام مستندات محروقة وصفوف يتيمة عند فشل لاحق | تحويله إلى `flush`-only؛ نقل الـ commit إلى مسار الحفظ اليدوي في `routes/owner/settings.py` | حذف سطر الانتهاك من `txn_boundaries_baseline.txt`؛ البوابة 44/44 |
| 3 | **P1** | `donation_gl_service` يحلّ حساب البنك بدون فرع ويُرحّل بـ `branch_id=None` → **كل تبرعات التينانت تُرفض** على خريطة مُهيّأة (الحساب `1120-B<n>` مرتبط بفرع) | حلّ فرع الحساب عبر `GLService.resolve_liquidity_branch` وختم القيد به، وتصحيح عملة القيد | `POST_RESULT True` مع قيد متوازن على قاعدة مُهيّأة |
| 4 | **P1** | `azad_subscription_fee_service.record_payment` يمرّر مفهوم `CASH`/`BANK` إلى `_resolve_journal_line_account` بدون رمز حساب → `GLMappingError` في كل عملية سداد | استخدام `GLService.get_payment_credit_account(...)` | 3 اختبارات محدّثة + 78/78 نجحت |
| 5 | **P1** | `return_service` يقبل `manual_refund_amount` غير مقيّد → كاشير بصلاحية `manage_sales` يخلق رصيد زبون ومرتجع إيراد من لا شيء | تحديده بـ `[0, auto_gross_return_amount]` | اختبار جديد `test_manual_refund_capped_at_returnable_amount` |
| 6 | **P2** | `SaleService.prepare_split_payments` يُسقط `rate_source`/`rate_fetched_at` → كل الدفع المقسّم يفقد توثيق مصدر السعر الذي أضفته الهجرة `k3l4m5n6o7p8` | نسخ الحقلين في كل دفعة | اختبار جديد + 62/62 نجحت |
| 7 | **P2** | قيود الأصول الثابتة تُوسم بعملة `AED` افتراضياً حتى على تينانت `ILS` | تمرير `currency=base_currency` و`exchange_rate=1` | `test_fixed_asset_cov` + 50/50 نجحت |

---

## 3. findings مفتوحة تحتاج قرار إدارة/منتج

| # | الخطورة | الموضوع | الأثر والتوصية |
|---|---|---|---|
| A | **P1** | **باقي زبون نقدي POS محسوب مرتين**: الزبون يدفع 100 لفاتورة 90 ويستلم 10 باقياً؛ الدرج يُسجّل صافي +90، لكن `SaleService` يُثبت الـ 10 كـ `prepayment` (دينار/شيك للزبون + مدين نقدية). الخصم يخرج من الدرج **ويبقى رصيداً للزبون** | توصية المحاسب: للدفع النقدي تحديداً، لا تُنشأ `Payment(prepayment)` للزيادة؛ إمّا تقيدها بحساب «باقي نقدي» مقابل النقدية، أو تُحفظ كـ `total_change_given` فقط. **لم أغيّره لأنه قرار منتج/سياسة سابقة معلّقة.** |
| B | **P2** | `/pos/api/cash-movements` و`/returns/api/create` بلا `Idempotency-Key` | إعادة محاولة العميل بعد انقطاع تُكرّر حركة الدرج أو المرتجع. التوصية: نفس نمط `api_checkout`/`api_pos_return_create`. |
| C | **P2** | `donation_gl_service:79` سعر احتياطي ثابت `3.67` عند فشل الجلب؛ `Donation` لا يخزّن سعراً | قد يُبالغ في قيد التبرع بعامل الفشل. التوصية: تخزين `rate_source`/`exchange_rate` على `Donation` (هجرة) أو رفض الترحيل عند غياب السعر بدل تخمينه. |
| D | **P2** | تقارير تحليلية تجمع `func.sum(SaleLine.line_total)` / `Sale.total_amount` بعملة المستند دون تحويل (`ai_service.py:1973,2130`, `ai_executor.py:591,616`, `reports_query_service.py:875`) | لا تؤثر على دفتر اليومية، لكنها تخلط العملات في شاشات التحليل. التوصية: `amount_aed` أو `line_total * exchange_rate`. |
| E | **P2** | صلاحية `assets:manage` ممنوحة فقط لـ `owner`/`super_admin`/`developer` | لا يستطيع مدير التينانت إدارة أصوله الثابتة عبر الواجهة. قرار RBAC. |

---

## 4. البوابات

`ruff`، `ruff format`، `mypy`، 87 مراجعة هجرة، `check_txn_boundaries` (44/44)، `check_service_side_effects`، القوالب، i18n، cspell، `check_api_docs`، و**مدقق الضمان الكامل `ASSURANCE=0`** (67 pytest + vitest + e2e).

> التنفيذ محلي بالكامل — بدون push.
