# Data Protection Policy | سياسة حماية البيانات

## 1. Purpose | الغرض

**EN:** This policy defines how AZAD Intelligent Systems collects, processes, stores, and destroys data in compliance with the UAE Personal Data Protection Law (PDPL) and international best practices.
**AR:** تحدد هذه السياسة كيفية جمع شركة أزاد للأنظمة الذكية ومعالجة وتخزين وتدمير البيانات بما يتوافق مع قانون حماية البيانات الشخصية في الإمارات (PDPL) والممارسات العالمية.

## 2. Data Classification | تصنيف البيانات

| Class (EN) | الفئة (AR) | Examples | الأمثلة | Protection Level | مستوى الحماية |
|------------|-----------|----------|---------|-----------------|---------------|
| Public | عام | Website content, pricing, marketing | محتوى الموقع، التسعير، التسويق | Standard | قياسي |
| Internal | داخلي | Employee directories, API documentation | أدلة الموظفين، مستندات API | Internal access only | وصول داخلي فقط |
| Confidential | سري | Customer databases, financial reports | قواعد بيانات العملاء، التقارير المالية | Encryption + RBAC | تشفير + RBAC |
| Restricted | مقيّد | Card vault, passwords, encryption keys | خزينة البطاقات، كلمات المرور، مفاتيح التشفير | Encryption + MFA + HSM | تشفير + MFA + HSM |

## 3. Data Collection | جمع البيانات

### 3.1 Lawful Basis | الأساس القانوني

| Basis (EN) | الأساس (AR) | Context | السياق |
|------------|-------------|---------|--------|
| Contract | العقد | Processing necessary to deliver Azadexa ERP | المعالجة الضرورية لتقديم أزادكسا ERP |
| Legal obligation | الالتزام القانوني | Tax records, regulatory reporting | سجلات الضريبة، الإبلاغ التنظيمي |
| Legitimate interest | المصلحة المشروعة | Fraud detection, platform security | كشف الاحتيال، أمان المنصة |
| Consent | الموافقة | Marketing emails, optional AI features | رسائل التسويق، ميزات AI الاختيارية |

### 3.2 Minimization | التقليل

**EN:** AZAD collects only the data necessary for the stated purpose. No data is collected for speculative future use.
**AR:** تجمع أزاد البيانات الضرورية فقط للغرض المُعلن. لا تجمع بيانات لاستخدام مستقبلي تخميني.

### 3.3 Tenant Data | بيانات المستأجر

**EN:** The Customer (tenant owner) is the data controller for data entered by their Users. AZAD is the data processor. Both parties are jointly responsible for compliance.
**AR:** العميل (مالك المستأجر) هو المسيطر على البيانات للبيانات المُدخلة من مستخدميه. أزاد هي معالج البيانات. الطرفان مسؤولان مشتركين عن الامتثال.

## 4. Data Processing | معالجة البيانات

### 4.1 Tenant Isolation | عزل المستأجرين

**EN:**
- Data is logically separated by `tenant_id` in every database table.
- ORM auto-scoping (`utils/tenant_orm.py`) prevents cross-tenant leakage.
- Raw SQL requires explicit `tenant_id` filtering.

**AR:**
- يتم الفصل المنطقي للبيانات بواسطة `tenant_id` في كل جدول قاعدة بيانات.
- نطاق ORM التلقائي (`utils/tenant_orm.py`) يمنع التسرب عبر المستأجرين.
- يتطلب SQL الخام تصفية `tenant_id` صريحة.

### 4.2 Processing Integrity | سلامة المعالجة

**EN:**
- Multi-model writes use `atomic_transaction` (`utils/db_safety.py`) to ensure consistency.
- Audit logs (`AuditLog` model) record every create, update, and delete.
- GL postings are immutable once finalized.

**AR:**
- تستخدم الكتابات متعددة الموديلات `atomic_transaction` (`utils/db_safety.py`) لضمان الاتساق.
- تسجل سجلات التدقيق (نموذج `AuditLog`) كل إنشاء وتحديث وحذف.
- ترحيلات GL غير قابلة للتغيير بمجرد الإنهاء.

### 4.3 Automated Decision-Making | اتخاذ القرار الآلي

**EN:** The AI assistant provides recommendations (pricing, stock levels) but does not make autonomous decisions affecting legal or financial outcomes. All AI actions are gated by human confirmation (`confirm_required` in `ActionDispatcher`).
**AR:** يقدم المساعد الذكي توصيات (تسعير، مستويات المخزون) لكنه لا يتخذ قرارات مستقلة تؤثر على النتائج القانونية أو المالية. جميع إجراءات AI تخضع لتأكيد بشري (`confirm_required` في `ActionDispatcher`).

## 5. Data Storage | تخزين البيانات

### 5.1 Primary Storage | التخزين الأساسي

| Type (EN) | النوع (AR) | Location | الموقع | Encryption | التشفير |
|-----------|-----------|----------|--------|------------|---------|
| Application database | قاعدة بيانات التطبيق | UAE data center | مركز بيانات الإمارات | AES-256 at rest | AES-256 في الراحة |
| File uploads | تحميلات الملفات | Object storage (S3-compatible) | تخزين كائن (متوافق S3) | Server-side encryption | تشفير من جانب الخادم |
| Session data | بيانات الجلسة | Redis | Redis | In-memory only, no persistence | في الذاكرة فقط، لا استمرارية |
| Logs | السجلات | Encrypted log aggregation | تجميع سجلات مشفر | TLS in transit | TLS أثناء النقل |

### 5.2 Backup Storage | تخزين النسخ الاحتياطية

| Backup (EN) | النسخ (AR) | Frequency | التكرار | Retention | الاحتفاظ | Location | الموقع |
|-------------|-----------|-----------|---------|-----------|----------|----------|--------|
| Full DB snapshot | لقطة DB كاملة | Daily | يومي | 30 days | 30 يوماً | Same region | نفس المنطقة |
| Incremental WAL | WAL تزايدي | Continuous | مستمر | 7 days | 7 أيام | Same region | نفس المنطقة |
| Scoped export | تصدير نطاقي | Weekly | أسبوعي | 90 days | 90 يوماً | Same region | نفس المنطقة |
| Off-site archive | أرشيف خارج الموقع | Monthly | شهري | 1 year | سنة | Secondary region | منطقة ثانوية |

**EN:** All backups are encrypted with AES-256-GCM using HSM-backed keys.
**AR:** جميع النسخ الاحتياطية مشفرة بـ AES-256-GCM باستخدام مفاتيح مدعومة بـ HSM.

### 5.3 Data Localization | توطين البيانات

**EN:** Tenant data is stored in the UAE by default. If a Customer requests data residency in another jurisdiction, AZAD will assess feasibility on a case-by-case basis.
**AR:** تُخزّن بيانات المستأجر في الإمارات افتراضياً. إذا طلب العميل إقامة بيانات في ولاية قضائية أخرى، ستقوم أزاد بتقييم الجدوى حالة بحالة.

## 6. Data Retention and Disposal | الاحتفاظ بالبيانات والتخلص

| Data Type (EN) | نوع البيانات | Retention | الاحتفاظ | Disposal Method | طريقة التخلص |
|----------------|-------------|-----------|----------|-----------------|--------------|
| Active tenant data | بيانات المستأجر النشط | Subscription duration + 30 days export window | مدة الاشتراك + 30 يوماً نافذة تصدير | Logical deletion + DB vacuum | حذف منطقي + تفريغ DB |
| Deleted tenant data | بيانات المستأجر المحذوف | 90 days after deletion | 90 يوماً بعد الحذف | Cryptographic erasure | محو تشفيري |
| Audit logs | سجلات التدقيق | 2 years | سنتان | Archive then shred | أرشفة ثم تمزيق |
| Payment records | سجلات المدفوعات | 7 years (tax compliance) | 7 سنوات (الامتثال الضريبي) | Archive then shred | أرشفة ثم تمزيق |
| Error logs | سجلات الأخطاء | 90 days | 90 يوماً | Automatic purge | تطهير آلي |
| Backups | النسخ الاحتياطية | Per backup policy | حسب سياسة النسخ | Secure deletion with verification | حذف آمن مع التحقق |

**EN:** Upon tenant deletion: 1. Data is immediately soft-deleted (hidden from UI). 2. After 30 days, hard-deleted from the active database. 3. After 90 days, purged from all backups and archives. 4. A certificate of destruction is available on request.
**AR:** عند حذف المستأجر: 1. يتم حذف البيانات فوراً بشكل ناعم (مخفية من واجهة المستخدم). 2. بعد 30 يوماً، حذف صارم من قاعدة البيانات النشطة. 3. بعد 90 يوماً، تطهير من جميع النسخ الاحتياطية والأرشيفات. 4. شهادة التدمير متاحة عند الطلب.

## 7. Data Subject Rights | حقوق الأفراد

| Right (EN) | الحق (AR) | How to Exercise | كيفية الممارسة |
|------------|-----------|-----------------|----------------|
| Access | الوصول | Request an export of all Data associated with the Tenant | طلب تصدير جميع البيانات المرتبطة بالمستأجر |
| Rectification | التصحيح | Update Data directly within the Service | تحديث البيانات مباشرة داخل الخدمة |
| Erasure | الحذف | Request Tenant deletion via support | طلب حذف المستأجر عبر الدعم |
| Portability | قابلية النقل | Export Data in JSON or Excel format | تصدير البيانات بصيغة JSON أو Excel |
| Restriction | التقييد | Contact AZAD support to freeze processing | التواصل مع دعم أزاد لتجميد المعالجة |
| Objection | الاعتراض | Unsubscribe from marketing emails | إلغاء الاشتراك من رسائل البريد التسويقية |

**EN:** Requests are processed within 30 days.
**AR:** تتم معالجة الطلبات خلال 30 يوماً.

## 8. Data Sharing and Transfers | مشاركة البيانات والنقل

### 8.1 Third Parties | الأطراف الثالثة

**EN:** AZAD shares data only with: Payment processors (Stripe, NOWPayments) under DPA; Cloud infrastructure providers under DPA; Law enforcement when legally compelled by a valid court order.
**AR:** تشارك أزاد البيانات فقط مع: معالجات المدفوعات (Stripe، NOWPayments) بموجب DPA؛ مزودي البنية التحتية السحابية بموجب DPA؛ إنفاذ القانون عندما يُجبر قانونياً بأمر محكمة صالح.

### 8.2 International Transfers | النقل الدولي

**EN:** If data must leave the UAE: Transfer is limited to countries with adequate data protection (EU adequacy decisions or SCCs), encryption during transfer, limitation to jurisdictions with strong data protection laws.
**AR:** إذا كان يجب مغادرة البيانات الإمارات: يقتصر النقل على دول ذات حماية بيانات كافية (قرارات كفاية الاتحاد الأوروبي أو SCCs)، التشفير أثناء النقل، التقييد على الولايات القضائية ذات قوانين حماية البيانات القوية.

## 9. Data Breach Response | الاستجابة لاختراق البيانات

### 9.1 Detection | الكشف

**EN:** Automated monitoring for unusual access patterns. Regular penetration testing. Employee reporting channel.
**AR:** مراقبة آلية للأنماط غير الاعتيادية للوصول. اختبارات اختراق منتظمة. قناة إبلاغ الموظفين.

### 9.2 Response Timeline | جدول الاستجابة

| Phase (EN) | المرحلة (AR) | Time | الوقت | Action | الإجراء |
|------------|-------------|------|-------|--------|---------|
| Detection | الكشف | Ongoing | مستمر | Automated alerts + manual review | تنبيهات آلية + مراجعة يدوية |
| Containment | الحصر | 1 hour | ساعة | Isolate affected systems | عزل الأنظمة المتأثرة |
| Assessment | التقييم | 4 hours | 4 ساعات | Determine scope and impact | تحديد النطاق والتأثير |
| Notification | الإشعار | 24 hours | 24 ساعة | Notify affected tenants and regulator if required | إشعار المستأجرين المتأثرين والمنظم إذا لزم |
| Remediation | العلاج | 72 hours | 72 ساعة | Patch, rotate credentials, restore systems | تصحيح، تدوير بيانات الاعتماد، استعادة الأنظمة |
| Post-mortem | ما بعد الوفاة | 7 days | 7 أيام | Root cause analysis + preventive measures | تحليل السبب الجذري + إجراءات وقائية |

## 10. Training and Awareness | التدريب والوعي

| Training (EN) | التدريب (AR) | Audience | الجمهور | Frequency | التكرار |
|---------------|-------------|----------|---------|-----------|---------|
| Data protection awareness | التوعية بحماية البيانات | All employees | جميع الموظفين | Annual | سنوي |
| PDPL compliance | الامتثال لـ PDPL | All employees | جميع الموظفين | Annual | سنوي |
| Secure coding | البرمجة الآمنة | Engineers | المهندسون | Quarterly | ربع سنوي |
| Incident response | الاستجابة للحوادث | Security team | فريق الأمان | Semi-annual | نصف سنوي |

## 11. Policy Review | مراجعة السياسة

**EN:** This policy is reviewed annually and whenever there is a significant change in regulations or business operations.
**AR:** تُراجع هذه السياسة سنوياً وكلما كان هناك تغيير كبير في اللوائح أو العمليات التجارية.

## 12. Contact | التواصل

Data Protection Officer (acting): Eng. Ahmad Ghannam | مسؤول حماية البيانات (بالإنابة): م. أحمد غنام
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
