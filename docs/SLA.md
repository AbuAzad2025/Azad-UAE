# Service Level Agreement (SLA) — اتفاقية مستوى الخدمة

## 1. Service Commitment | التزام الخدمة

**EN:** AZAD Intelligent Systems commits to the following service levels for the Azadexa ERP SaaS platform.
**AR:** تلتزم شركة أزاد للأنظمة الذكية بمستويات الخدمة التالية لمنصة أزادكسا ERP SaaS.

| Metric (EN) | المقياس (AR) | Target | الهدف | Measurement Period | فترة القياس |
|-------------|-------------|--------|-------|-------------------|-------------|
| Uptime | مدة التشغيل | 99.9% | 99.9% | Calendar month | الشهر التقويمي |
| API availability | توفر API | 99.95% | 99.95% | Calendar month | الشهر التقويمي |
| Data durability | متانة البيانات | 99.99% | 99.99% | Annual | السنوي |

**EN:** Uptime is calculated as: `(Total minutes in month - Downtime minutes) / Total minutes in month * 100`. Excluded from downtime: scheduled maintenance windows (announced 72 hours in advance), force majeure, third-party service failures outside AZAD's control, customer-caused issues.

**AR:** يتم حساب مدة التشغيل كـ: `(إجمالي الدقائق في الشهر - دقائق التوقف) / إجمالي الدقائق في الشهر * 100`. مستثنى من التوقف: نوافذ الصيانة المجدولة (مُعلنة مسبقاً بـ 72 ساعة)، القوة القاهرة، إخفاقات خدمات طرف ثالث خارجة عن سيطرة أزاد، المشاكل الناتجة عن العميل.

## 2. Scheduled Maintenance | الصيانة المجدولة

| Type (EN) | النوع (AR) | Frequency | التكرار | Notice | الإشعار | Duration | المدة |
|-----------|-----------|-----------|---------|--------|---------|----------|-------|
| Routine | روتينية | Weekly | أسبوعية | 72 hours | 72 ساعة | Up to 2 hours | حتى ساعتان |
| Major release | إصدار رئيسي | Quarterly | ربع سنوية | 7 days | 7 أيام | Up to 4 hours | حتى 4 ساعات |
| Emergency patch | تصحيح طارئ | As needed | حسب الحاجة | 4 hours | 4 ساعات | Up to 1 hour | حتى ساعة |

**EN:** All maintenance is conducted during the low-usage window: 02:00–06:00 GST (UTC+4).
**AR:** تُجرى جميع أعمال الصيانة خلال نافذة الاستخدام المنخفض: 02:00–06:00 توقيت دبي (UTC+4).

## 3. Support Response Times | أوقات استجابة الدعم

| Severity (EN) | الخطورة (AR) | Definition | التعريف | Initial Response | الاستجابة الأولى | Resolution Target | هدف الحل | Communication Channel | قناة التواصل |
|-----------------|-------------|------------|---------|-----------------|------------------|-------------------|----------|----------------------|-------------|
| P1 — Critical | P1 — حرج | Service completely unavailable; data loss risk | الخدمة غير متوفرة تماماً؛ خطر فقدان البيانات | 15 minutes | 15 دقيقة | 4 hours | 4 ساعات | Phone + Email + WhatsApp | هاتف + بريد + واتساب |
| P2 — High | P2 — عالي | Major feature unusable; significant business impact | ميزة رئيسية غير قابلة للاستخدام؛ تأثير تجاري كبير | 1 hour | ساعة | 8 hours | 8 ساعات | Email + WhatsApp | بريد + واتساب |
| P3 — Medium | P3 — متوسط | Partial feature degradation; workaround exists | تدهور جزئي في الميزة؛ يوجد حل بديل | 4 hours | 4 ساعات | 48 hours | 48 ساعة | Email + Ticket | بريد + تذكرة |
| P4 — Low | P4 — منخفض | Cosmetic issue; question; enhancement request | مشكلة شكلية؛ سؤال؛ طلب تحسين | 24 hours | 24 ساعة | 7 days | 7 أيام | Ticket | تذكرة |

**EN:** Response time is measured from the moment AZAD acknowledges the ticket.
**AR:** يتم قياس وقت الاستجابة من لحظة إقرار أزاد بالتذكرة.

## 4. Support Hours | ساعات الدعم

| Channel (EN) | القناة (AR) | Hours | الساعات | Days | الأيام |
|--------------|------------|-------|---------|------|--------|
| Phone / WhatsApp | الهاتف / واتساب | 08:00–20:00 GST | 08:00–20:00 توقيت دبي | Sunday–Thursday | الأحد–الخميس |
| Email / Ticket | البريد / التذكرة | 24/7 | 24/7 | All days | جميع الأيام |

**EN:** P1 issues receive 24/7 response regardless of channel.
**AR:** تحصل مشكلات P1 على استجابة 24/7 بغض النظر عن القناة.

## 5. Service Credits | أرصدة الخدمة

**EN:** If AZAD fails to meet the monthly uptime target, the Customer is entitled to service credits applied to the next billing cycle.
**AR:** إذا فشلت أزاد في تحقيق هدف مدة التشغيل الشهرية، يحق للعميل الحصول على أرصدة خدمة تُطبق على دورة الفوترة التالية.

| Uptime Miss (EN) | التقصير في التشغيل | Credit | الرصيد |
|-------------------|---------------------|--------|--------|
| < 99.9% but ≥ 99.0% | < 99.9% لكن ≥ 99.0% | 5% of monthly fee | 5% من الرسوم الشهرية |
| < 99.0% but ≥ 95.0% | < 99.0% لكن ≥ 95.0% | 15% of monthly fee | 15% من الرسوم الشهرية |
| < 95.0% | < 95.0% | 50% of monthly fee | 50% من الرسوم الشهرية |

**EN:** Credits are the sole and exclusive remedy for SLA failures. Credits do not exceed 100% of one monthly fee. To claim credits, the Customer must submit a request within 15 days of the missed month with documented evidence.
**AR:** الأرصدة هي العلاج الوحيد والحصري لإخفاقات SLA. لا تتجاوز الأرصدا 100% من رسوم شهر واحد. للمطالبة بالأرصدة، يجب على العميل تقديم طلب خلال 15 يوماً من الشهر المُخفق مع دليل موثق.

## 6. Data Backup and Recovery | النسخ الاحتياطي والاستعادة

| Backup Type (EN) | نوع النسخ | Frequency | التكرار | Retention | الاحتفاظ | RPO | RPO | RTO | RTO |
|------------------|-----------|-----------|---------|-----------|----------|-----|-----|-----|-----|
| Database snapshot | لقطة قاعدة البيانات | Daily | يومي | 30 days | 30 يوماً | 24 hours | 24 ساعة | 4 hours | 4 ساعات |
| Incremental WAL | WAL التزايدي | Continuous | مستمر | 7 days | 7 أيام | Near-zero | شبه صفر | 2 hours | ساعتان |
| Full scoped export | تصدير نطاقي كامل | Weekly | أسبوعي | 90 days | 90 يوماً | 7 days | 7 أيام | 8 hours | 8 ساعات |
| Off-site archive | أرشيف خارج الموقع | Monthly | شهري | 1 year | سنة | 30 days | 30 يوماً | 24 hours | 24 ساعة |

**EN:** All backups are encrypted with AES-256 and stored in geographically separate locations.
**AR:** جميع النسخ الاحتياطية مشفرة بـ AES-256 ومخزنة في مواقع جغرافية منفصلة.

## 7. Security Incidents | الحوادث الأمنية

| Incident Type (EN) | نوع الحدث | Notification Time | وقت الإشعار | Action | الإجراء |
|----------------------|-----------|-------------------|-------------|--------|---------|
| Confirmed data breach | اختراق بيانات مؤكد | Within 24 hours | خلال 24 ساعة | Email + phone to Customer admin | بريد + هاتف لمسؤول العميل |
| Suspected breach | اختراق مشتبه | Within 4 hours | خلال 4 ساعات | Ticket + monitoring escalation | تذكرة + تصعيد المراقبة |
| Platform-wide vulnerability | ثغرة على مستوى المنصة | Within 2 hours | خلال ساعتين | In-app banner + email to all admins | لافتة داخل التطبيق + بريد لجميع المسؤولين |

## 8. Performance Benchmarks | معايير الأداء

| Endpoint (EN) | نقطة النهاية | p95 Response Time | وقت الاستجابة p95 |
|--------------|-------------|-------------------|-------------------|
| Dashboard load | تحميل لوحة التحكم | < 800 ms | < 800 مللي ثانية |
| Sale creation | إنشاء مبيعة | < 1.5 s | < 1.5 ثانية |
| POS checkout | الدفع في نقاط البيع | < 2 s | < 2 ثانية |
| Report generation | إنشاء التقرير | < 5 s | < 5 ثوانٍ |
| API response (stock sync) | استجابة API (مزامنة المخزون) | < 500 ms | < 500 مللي ثانية |
| AI chat response | استجابة محادثة AI | < 3 s | < 3 ثوانٍ |

## 9. Escalation Path | مسار التصعيد

| Level (EN) | المستوى (AR) | Role | الدور | Contact | التواصل |
|------------|-------------|------|-------|---------|---------|
| L1 | L1 | Support Engineer | مهندس دعم | support@azadsystems.com | support@azadsystems.com |
| L2 | L2 | Senior Engineer | مهندس أول | senior@azadsystems.com | senior@azadsystems.com |
| L3 | L3 | CTO / Product Lead | CTO / رئيس المنتج | cto@azadsystems.com | cto@azadsystems.com |
| Executive | تنفيذي | CEO | CEO | rafideen.ahmadghannam@gmail.com | rafideen.ahmadghannam@gmail.com |

**EN:** Escalation from L1 to L2 occurs automatically if a P1 or P2 ticket is unresolved within 50% of the target resolution time.
**AR:** يحدث التصعيد من L1 إلى L2 تلقائياً إذا لم تُحل تذكرة P1 أو P2 خلال 50% من وقت الحل المستهدف.

## 10. SLA Exclusions | استثناءات SLA

**EN:** The SLA does not apply to: Beta, trial, or demo Tenants; features marked as "Experimental" or "Beta" in the UI; performance degradation caused by Customer actions (e.g., importing 1M rows in one batch); failures of Customer-managed integrations (custom webhooks, external APIs).

**AR:** لا تنطبق SLA على: المستأجرين التجريبيين أو التجريبيين أو العرض التوضيحيين؛ الميزات المُعلّمة بـ "تجريبي" أو "Beta" في واجهة المستخدم؛ تدهور الأداء الناتج عن إجراءات العميل (مثل استيراد مليون صف في دفعة واحدة)；إخفاقات التكاملات المُدارة من العميل (webhooks مخصصة، APIs خارجية).

## 11. Review and Changes | المراجعة والتغييرات

**EN:** This SLA is reviewed quarterly. Changes are communicated 30 days in advance.
**AR:** تُراجع SLA ربع سنوياً. يتم التواصل عن التغييرات مسبقاً بـ 30 يوماً.

## 12. Contact | التواصل

AZAD Intelligent Systems | شركة أزاد للأنظمة الذكية
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
