# FAQ — Technical Support | الأسئلة الشائعة — الدعم الفني

## 1. Access and Authentication | الوصول والاستيثاق

**Q (EN):** I forgot my password.
**Q (AR):** نسيت كلمة المرور.
**A (EN):** Click "Forgot Password" on the login page. Enter your email. A reset link will be sent within 2 minutes. If you do not receive it, check spam or contact support.
**A (AR):** اضغط "نسيت كلمة المرور" على صفحة تسجيل الدخول. أدخل بريدك. سيتم إرسال رابط إعادة التعيين خلال دقيقتين. إذا لم تتلقه، تحقق من الرسائل غير المرغوب فيها أو اتصل بالدعم.

**Q (EN):** My account is locked.
**Q (AR):** حسابي مقفل.
**A (EN):** Accounts lock after 5 failed login attempts. Wait 15 minutes or contact your admin to unlock. If you are the owner, contact support with proof of identity.
**A (AR):** تُقفل الحسابات بعد 5 محاولات فاشلة لتسجيل الدخول. انتظر 15 دقيقة أو اتصل بمسؤولك لفتح القفل. إذا كنت المالك، اتصل بالدعم بإثبات هوية.

**Q (EN):** How do I enable two-factor authentication?
**Q (AR):** كيف أفعّل المصادقة الثنائية؟
**A (EN):** 2FA is available for owner and admin accounts. Go to Settings → Security → Enable 2FA. Scan the QR code with Google Authenticator or Authy.
**A (AR):** 2FA متاحة لحسابات المالك والمسؤول. اذهب إلى الإعدادات → الأمان → تفعيل 2FA. امسح QR Code بـ Google Authenticator أو Authy.

## 2. Data and Display | البيانات والعرض

**Q (EN):** My data is not showing.
**Q (AR):** بياناتي لا تظهر.
**A (EN):** Check: ensure you are in the correct branch (top-right selector); check date filters on the report or list; clear browser cache (Ctrl+Shift+R); if still missing, verify the data was saved successfully (check audit logs).
**A (AR):** تحقق: تأكد من أنك في الفرع الصحيح (محدد الأعلى اليمين)；تحقق من فلاتر التاريخ على التقرير أو القائمة؛ امسح ذاكرة التخزين المؤقت للمتصفح (Ctrl+Shift+R)；إذا كان لا يزال مفقوداً، تحقق من أن البيانات حُفظت بنجاح (تحقق من سجلات التدقيق).

**Q (EN):** Numbers look wrong (e.g., 1,000 shown as 1).
**Q (AR):** الأرقام تبدو خاطئة (مثل 1,000 تظهر كـ 1).
**A (EN):** Check your browser locale and the system's decimal separator setting (Settings → Regional). Arabic locales use comma as decimal separator.
**A (AR):** تحقق من إعدادات لغة المتصفح والنظام للفاصل العشري (الإعدادات → الإقليمية). تستخدم اللغات العربية الفاصلة كفاصل عشري.

## 3. Sales and Invoices | المبيعات والفواتير

**Q (EN):** I created a sale but the stock did not deduct.
**Q (AR):** أنشأت مبيعة لكن المخزون لم يُخصم.
**A (EN):** Stock deducts when the sale status is "Confirmed" or "Paid". If the sale is still "Draft", confirm it. If the product is a service (non-stock), no deduction occurs.
**A (AR):** يخصم المخزون عندما تكون حالة المبيعة "مؤكدة" أو "مدفوعة". إذا كانت المبيعة لا تزال "مسودة"، أكدها. إذا كان المنتج خدمة (غير مخزون)، لا يحدث خصم.

**Q (EN):** Can I edit an invoice after printing?
**Q (AR):** هل يمكنني تعديل فاتورة بعد الطباعة؟
**A (EN):** Invoices marked as "Finalized" cannot be edited. You must create a credit note or return. Go to Sales → Returns.
**A (AR):** الفواتير المُعلّمة بـ "مُنهية" لا يمكن تعديلها. يجب إنشاء إشعار دائن أو إرجاع. اذهب إلى مبيعات → إرجاعات.

**Q (EN):** How do I add a discount to an invoice?
**Q (AR):** كيف أضيف خصماً إلى فاتورة؟
**A (EN):** In the sale form, click "Discount" and enter percentage or fixed amount. Ensure you have permission `apply_discount`.
**A (AR):** في نموذج المبيعة، اضغط "خصم" وأدخل نسبة أو مبلغ ثابت. تأكد من أن لديك إذن `apply_discount`.

## 4. Inventory | المخزون

**Q (EN):** How do I add a new warehouse?
**Q (AR):** كيف أضيف مستودعاً جديداً؟
**A (EN):** Go to Warehouses → New. Enter name, code, and branch. Only users with `manage_warehouses` permission can add warehouses.
**A (AR):** اذهب إلى المستودعات → جديد. أدخل الاسم والكود والفرع. يمكن فقط للمستخدمين الذين لديهم إذن `manage_warehouses` إضافة مستودعات.

**Q (EN):** How do I transfer stock between branches?
**Q (AR):** كيف أنقل مخزوناً بين الفروع؟
**A (EN):** Go to Inventory → Transfer. Select source and destination warehouses, add products and quantities. The transfer creates two movements: deduct from source, add to destination.
**A (AR):** اذهب إلى المخزون → نقل. اختر مستودعات المصدر والوجهة، أضف منتجات وكميات. ينشئ النقل حركتين: خصم من المصدر، إضافة إلى الوجهة.

**Q (EN):** My physical count does not match the system.
**Q (AR):** عددي الفعلي لا يتطابق مع النظام.
**A (EN):** Go to Inventory → Reconciliation. Select the warehouse and product. Enter the actual count. The system calculates the difference and suggests an adjustment journal entry.
**A (AR):** اذهب إلى المخزون → تسوية. اختر المستودع والمنتج. أدخل العدد الفعلي. يحسب النظام الفرق ويقترح قيد تعديل.

**Q (EN):** What is WAC and why did my cost price change?
**Q (AR):** ما هو WAC ولماذا تغير سعر التكلفة؟
**A (EN):** WAC (Weighted Average Cost) recalculates after every purchase receipt. This ensures your cost of goods sold reflects the average price paid. It is the default method. You can switch to FIFO in Settings → Inventory (Enterprise plan only).
**A (AR):** WAC (التكلفة المتوسطة المرجحة) تُعاد حسابها بعد كل إيصال شراء. هذا يضمن أن تكلفة البضاعة المباعة تعكس متوسط السعر المدفوع. إنها الطريقة الافتراضية. يمكنك التبديل إلى FIFO في الإعدادات → المخزون (باقة المؤسسات فقط).

## 5. Payments and Cheques | المدفوعات والشيكات

**Q (EN):** How do I record a bounced cheque?
**Q (AR):** كيف أسجل شيكاً مرتدّاً؟
**A (EN):** Go to Cheques → select the cheque → Bounce. The system creates a reversal journal entry and updates the customer balance.
**A (AR):** اذهب إلى الشيكات → اختر الشيك → رد. ينشئ النظام قيداً عكسياً ويحدّث رصيد العميل.

**Q (EN):** Can I accept partial payment for an invoice?
**Q (AR):** هل يمكنني قبول دفع جزئي لفاتورة؟
**A (EN):** Yes. In the payment screen, enter the partial amount. The invoice will show "Partially Paid" with the remaining balance.
**A (AR):** نعم. في شاشة الدفع، أدخل المبلغ الجزئي. ستظهر الفاتورة "مدفوعة جزئياً" مع الرصيد المتبقي.

**Q (EN):** How do I reconcile my bank account?
**Q (AR):** كيف أسوي حسابي البنكي؟
**A (EN):** Go to Banking → Reconciliation. Import your bank statement (CSV/Excel). The system matches transactions automatically. Unmatched items appear for manual review.
**A (AR):** اذهب إلى البنك → تسوية. استورد كشف حسابك (CSV/Excel). يطابق النظام المعاملات تلقائياً. تظهر العناصر غير المطابقة للمراجعة اليدوية.

## 6. POS | نقاط البيع

**Q (EN):** The POS is slow.
**Q (AR):** POS بطيء.
**A (EN):** Check internet connectivity. The POS caches product data locally. If the issue persists, contact support with the branch ID and timestamp.
**A (AR):** تحقق من اتصال الإنترنت. POS يخبّئ بيانات المنتجات محلياً. إذا استمرت المشكلة، اتصل بالدعم مع معرف الفرع والطابع الزمني.

**Q (EN):** Can I use POS offline?
**Q (AR):** هل يمكن استخدام POS offline؟
**A (EN):** Critical operations (create sale, print receipt) work offline for up to 2 hours. Data syncs automatically when connectivity returns. Full offline mode is on the roadmap.
**A (AR):** العمليات الحرجة (إنشاء مبيعة، طباعة إيصال) تعمل offline حتى ساعتين. تتزامن البيانات تلقائياً عند عودة الاتصال. وضع offline الكامل في خارطة الطريق.

**Q (EN):** How do I apply a promotion at POS?
**Q (AR):** كيف أطبق عرضاً في POS؟
**A (EN):** The promotion engine applies eligible promotions automatically at checkout. To force apply, click "Promotions" and select manually.
**A (AR):** يطبق محرك العروض العروض المؤهلة تلقائياً عند الدفع. للإجبار على التطبيق، اضغط "عروض" واختر يدوياً.

## 7. HR and Payroll | الموارد البشرية والرواتب

**Q (EN):** How do I calculate payroll?
**Q (AR):** كيف أحسب الرواتب؟
**A (EN):** Go to Payroll → Process. Select the month and employees. The system calculates basic salary, allowances, deductions, tax, and insurance. Review and confirm.
**A (AR):** اذهب إلى الرواتب → معالجة. اختر الشهر والموظفين. يحسب النظام الراتب الأساسي والبدلات والاستقطاعات والضريبة والتأمين. راجع وأكد.

**Q (EN):** Can I export payroll to WPS?
**Q (AR):** هل يمكنني تصدير الرواتب إلى WPS؟
**A (EN):** WPS export is on the roadmap (Q4 2026). Currently, export to Excel and upload manually.
**A (AR):** تصدير WPS في خارطة الطريق (Q4 2026). حالياً، صدّر إلى Excel وارفع يدوياً.

**Q (EN):** How do I record attendance?
**Q (AR):** كيف أسجل الحضور؟
**A (EN):** Employees check in via the attendance screen or biometric integration (roadmap). Manual entry is available for admins.
**A (AR):** يسجل الموظفون الدخول عبر شاشة الحضور أو التكامل البيومتري (خارطة الطريق). الإدخال اليدوي متاح للمسؤولين.

## 8. Reports | التقارير

**Q (EN):** How do I export a report to Excel?
**Q (AR):** كيف أصدر تقريراً إلى Excel؟
**A (EN):** On any report page, click the "Export" button (top-right). Choose Excel or PDF.
**A (AR):** في أي صفحة تقرير، اضغط زر "تصدير" (أعلى اليمين). اختر Excel أو PDF.

**Q (EN):** Can I schedule reports to email automatically?
**Q (AR):** هل يمكنني جدولة التقارير لإرسالها بالبريد تلقائياً؟
**A (EN):** Scheduled reports are available on Professional and Enterprise plans. Go to Reports → Scheduled → New.
**A (AR):** التقارير المجدولة متاحة في باقات الاحترافية والمؤسسات. اذهب إلى تقارير → مجدولة → جديد.

**Q (EN):** My trial balance does not balance.
**Q (AR):** ميزان مراجعتي لا يتوازن.
**A (EN):** This indicates a data integrity issue. Do not ignore it. Contact support immediately with the period and branch. We will run a diagnostic.
**A (AR):** هذا يشير إلى مشكلة سلامة بيانات. لا تهملها. اتصل بالدعم فوراً مع الفترة والفرع. سنشغّل تشخيصاً.

## 9. AI Assistant | المساعد الذكي

**Q (EN):** The AI gave a wrong answer.
**Q (AR):** أعطاني AI إجابة خاطئة.
**A (EN):** The AI recommendations are based on your data patterns and are advisory. Always verify critical decisions (pricing, orders) with a human manager. Report incorrect answers to improve the model.
**A (AR):** توصيات AI مبنية على أنماط بياناتك وهي استشارية. تحقق دائماً من القرارات الحرجة (تسعير، طلبات) مع مدير بشري. أبلغ عن إجابات خاطئة لتحسين النموذج.

**Q (EN):** Can the AI delete data?
**Q (AR):** هل يمكن لـ AI حذف البيانات؟
**A (EN):** No. The AI cannot create, edit, or delete records without explicit human confirmation. Sensitive actions are gated by `confirm_required` in the ActionDispatcher.
**A (AR):** لا. لا يمكن لـ AI إنشاء أو تعديل أو حذف سجلات دون تأكيد بشري صريح. الإجراءات الحساسة محمية بـ `confirm_required` في ActionDispatcher.

## 10. Integrations | التكاملات

**Q (EN):** How do I connect my external POS?
**Q (AR):** كيف أربط POS الخارجي؟
**A (EN):** Generate an API key in Settings → API Keys. Use the key with `POST /api/v2/stock/sync`. See `docs/INTEGRATION_GUIDE.md`.
**A (AR):** أنشئ مفتاح API في الإعدادات → مفاتيح API. استخدم المفتاح مع `POST /api/v2/stock/sync`. راجع `docs/INTEGRATION_GUIDE.md`.

**Q (EN):** Can I connect Shopify?
**Q (AR):** هل يمكنني ربط Shopify؟
**A (EN):** Shopify integration is on the roadmap (Q4 2026). Currently, use the API for custom integrations.
**A (AR):** تكامل Shopify في خارطة الطريق (Q4 2026). حالياً، استخدم API للتكاملات المخصصة.

## 11. Billing and Account | الفوترة والحساب

**Q (EN):** How do I upgrade my plan?
**Q (AR):** كيف أرتقي باقتي؟
**A (EN):** Contact your account manager or email billing@azadsystems.com.
**A (AR):** اتصل بمدير حسابك أو ارسل بريداً إلى billing@azadsystems.com.

**Q (EN):** How do I cancel?
**Q (AR):** كيف ألغي؟
**A (EN):** Submit a cancellation request 30 days in advance via email. You have 30 days to export data after cancellation.
**A (AR):** أرسل طلب إلغاء 30 يوماً مقدماً عبر البريد. لديك 30 يوماً لتصدير البيانات بعد الإلغاء.

## 12. Contact Support | التواصل مع الدعم

| Channel (EN) | القناة (AR) | Detail | التفصيل | Hours | الساعات |
|--------------|-------------|--------|----------|-------|---------|
| Email | البريد | support@azadsystems.com | support@azadsystems.com | 24/7 | 24/7 |
| WhatsApp | واتساب | +972 56 215 0193 | +972 56 215 0193 | 08:00–20:00 GST | 08:00–20:00 توقيت دبي |
| Phone | الهاتف | +972 56 215 0193 | +972 56 215 0193 | 08:00–20:00 GST | 08:00–20:00 توقيت دبي |
| Ticket | التذكرة | In-app Support → New Ticket | الدعم داخل التطبيق → تذكرة جديدة | 24/7 | 24/7 |

**EN:** Severity levels: P1 (System down): Call or WhatsApp immediately. P2 (Major feature broken): Email or WhatsApp. P3 (Question / Minor issue): Ticket or email.
**AR:** مستويات الخطورة: P1 (النظام معطل): اتصل أو ارسل واتساب فوراً. P2 (ميزة رئيسية معطلة): بريد أو واتساب. P3 (سؤال / مشكلة صغيرة): تذكرة أو بريد.
