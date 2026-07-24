# Security Policy | سياسة الأمان

## 1. Scope | النطاق

**EN:** This policy applies to all employees, contractors, and third-party vendors with access to Azadexa ERP systems, infrastructure, or customer data.
**AR:** تنطبق هذه السياسة على جميع الموظفين والمقاولين والبائعين من الأطراف الثالثة الذين لديهم وصول إلى أنظمة أزادكسا ERP أو البنية التحتية أو بيانات العملاء.

## 2. Security Principles | مبادئ الأمان

| Principle (EN) | المبدأ (AR) | Implementation | التنفيذ |
|---------------|-------------|----------------|---------|
| Defense in depth | الدفاع العميق | Multiple security layers: network, application, database, physical | طبقات أمان متعددة: شبكة، تطبيق، قاعدة بيانات، فيزيائي |
| Least privilege | أقل امتياز | Users and services receive only the minimum required access | يحصل المستخدمون والخدمات على الحد الأدنى من الوصول المطلوب |
| Zero trust | عدم الثقة الضمنية | No implicit trust based on network location | لا ثقة ضمنية بناءً على موقع الشبكة |
| Tenant isolation | عزل المستأجرين | Logical and query-level separation of tenant data | الفصل المنطقي على مستوى الاستعلام لبيانات المستأجر |
| Audit everything | تدقيق كل شيء | All access and changes are logged | يتم تسجيل كل وصول وتغيير |

## 3. Access Control | التحكم بالوصول

### 3.1 Authentication | الاستيثاق

| Layer (EN) | الطبقة (AR) | Mechanism | الآلية |
|------------|-------------|-----------|--------|
| Application | التطبيق | Username + password + optional 2FA | اسم المستخدم + كلمة المرور + 2FA اختياري |
| API | API | API key + secret (HMAC-signed requests) | مفتاح API + سر (طلبات موقعة HMAC) |
| Owner panel | لوحة المالك | Separate owner credentials with IP allowlisting | بيانات اعتماد مالك منفصلة مع قائمة سماح IP |

### 3.2 Password Policy | سياسة كلمات المرور

| Rule (EN) | القاعدة (AR) | Requirement | المتطلب |
|-----------|-------------|-------------|----------|
| Minimum length | الحد الأدنى للطول | 12 characters | 12 حرفاً |
| Complexity | التعقيد | Upper, lower, digit, special character | حرف كبير، صغير، رقم، حرف خاص |
| Rotation | التدوير | Every 90 days for admin accounts | كل 90 يوماً لحسابات المسؤولين |
| Reuse | إعادة الاستخدام | Last 5 passwords cannot be reused | لا يمكن إعادة استخدام آخر 5 كلمات مرور |
| Storage | التخزين | Argon2id hashing (never plain text) | تجزئة Argon2id (أبداً نصاً عادياً) |

### 3.3 Session Management | إدارة الجلسات

**EN:** Session timeout: 24 hours idle, 8 hours absolute for sensitive routes. Concurrent session limit: 3 per user. Session invalidation on password change or suspicious activity.
**AR:** مهلة الجلسة: 24 ساعة خمول، 8 ساعات مطلقة للمسارات الحساسة. حد الجلسات المتزامنة: 3 لكل مستخدم. إبطال الجلسة عند تغيير كلمة المرور أو نشاط مشبوه.

### 3.4 Role-Based Access Control | التحكم بالوصول المعتمد على الأدوار

| Role (EN) | الدور (AR) | Typical Permissions | الأذونات النموذجية |
|-----------|-----------|--------------------|---------------------|
| Owner | المالك | Full system access, billing, user management | وصول كامل للنظام، الفوترة، إدارة المستخدمين |
| Admin | المسؤول | All modules except billing and owner settings | جميع الوحدات باستثناء الفوترة وإعدادات المالك |
| Accountant | المحاسب | GL, payments, cheques, reports | GL، المدفوعات، الشيكات، التقارير |
| Sales Manager | مدير المبيعات | Sales, customers, POS, reports | المبيعات، العملاء، POS، التقارير |
| Cashier | الكاشير | POS only, limited to assigned branch | POS فقط، محدود للفرع المُخصّص |
| Warehouse | المستودع | Inventory, stock movements, transfers | المخزون، حركات المخزون، التحويلات |
| Viewer | المشاهد | Read-only access to assigned modules | وصول للقراءة فقط للوحدات المُخصّصة |

**EN:** Permissions are enforced via `@permission_required('code')` and verified at the service layer.
**AR:** يتم إنفاذ الأذونات عبر `@permission_required('code')` والتحقق منها على مستوى الخدمة.

## 4. Data Protection | حماية البيانات

### 4.1 Classification | التصنيف

| Level (EN) | المستوى (AR) | Examples | الأمثلة | Handling | المعالجة |
|------------|-------------|----------|---------|----------|----------|
| Public | عام | Marketing website, pricing page | موقع التسويق، صفحة التسعير | No restrictions | لا قيود |
| Internal | داخلي | API docs, system architecture | مستندات API، بنية النظام | Share internally only | المشاركة داخلياً فقط |
| Confidential | سري | Customer lists, revenue data | قوائم العملاء، بيانات الإيرادات | Encryption + RBAC | التشفير + RBAC |
| Restricted | مقيّد | Card vault, passwords, encryption keys | خزينة البطاقات، كلمات المرور، مفاتيح التشفير | Encryption + MFA + HSM | التشفير + MFA + HSM |

### 4.2 Encryption | التشفير

| State (EN) | الحالة (AR) | Method | الطريقة | Key Management | إدارة المفاتيح |
|------------|-------------|--------|---------|----------------|---------------|
| In transit | أثناء النقل | TLS 1.3 | TLS 1.3 | Let's Encrypt / Cloudflare | Let's Encrypt / Cloudflare |
| At rest (DB) | في الراحة (DB) | PostgreSQL TDE | PostgreSQL TDE | Cloud provider KMS | KMS مزود السحابة |
| At rest (backups) | في الراحة (النسخ الاحتياطية) | AES-256-GCM | AES-256-GCM | HSM-backed keys | مفاتيح مدعومة بـ HSM |
| Card data | بيانات البطاقة | Tokenization + AES-256 | Tokenization + AES-256 | PCI-compliant vault | خزينة متوافقة مع PCI |

### 4.3 Tenant Isolation | عزل المستأجرين

**EN:**
- Every database query is scoped by `tenant_id` via `tenant_query()`.
- ORM auto-scoping is registered in `utils/tenant_orm.py`.
- Cross-tenant access triggers 404 and logs a security alert.
- Raw SQL must append `tenant_id=<tid>` explicitly.

**AR:**
- يتم نطاق كل استعلام قاعدة بيانات بواسطة `tenant_id` عبر `tenant_query()`.
- يتم تسجيل نطاق ORM التلقائي في `utils/tenant_orm.py`.
- الوصول عبر المستأجرين يُشغّل 404 ويسجل تنبيه أمان.
- يجب أن يلحق SQL الخام `tenant_id=<tid>` صراحةً.

## 5. Application Security | أمان التطبيق

### 5.1 Input Validation | التحقق من المدخلات

**EN:**
- All JSON requests use `silent=True` and validate structure.
- All `Decimal` conversions guard against `None`.
- SQL injection is prevented via SQLAlchemy ORM and parameterized queries.
- XSS prevention via Jinja2 auto-escaping and CSP headers.

**AR:**
- تستخدم جميع طلبات JSON `silent=True` وتتحقق من الهيكل.
- تحمي جميع تحويلات `Decimal` من `None`.
- يتم منع حقن SQL عبر ORM SQLAlchemy والاستعلامات المُعاملية.
- منع XSS عبر الهروب التلقائي لـ Jinja2 ورؤوس CSP.

### 5.2 CSRF Protection | حماية CSRF

**EN:** All state-changing forms include CSRF tokens. API endpoints use API key authentication (no CSRF needed).
**AR:** تتضمن جميع النماذج التي تُغيّر الحالة رموز CSRF. تستخدم نقاط نهاية API استيثاق مفتاح API (لا حاجة لـ CSRF).

### 5.3 Dependency Management | إدارة الاعتماديات

**EN:** Dependencies are pinned in `requirements.txt` with hashes. Monthly automated vulnerability scanning via `safety` and `snyk`. Critical patches applied within 48 hours of release.
**AR:** الاعتماديات مُثبتة في `requirements.txt` مع تجزئات. فحص آلي شهري للثغرات عبر `safety` و `snyk`. تُطبّق التصحيحات الحرجة خلال 48 ساعة من الإصدار.

## 6. Infrastructure Security | أمان البنية التحتية

### 6.1 Network | الشبكة

**EN:** WAF (Web Application Firewall) for all public endpoints. DDoS protection via Cloudflare or equivalent. Private subnets for databases and internal services. VPN required for production access.
**AR:** WAF (جدار تطبيقات الويب) لجميع نقاط النهاية العامة. حماية DDoS عبر Cloudflare أو ما يعادلها. شبكات فرعية خاصة لقواعد البيانات والخدمات الداخلية. VPN مطلوب للوصول إلى الإنتاج.

### 6.2 Monitoring and Alerting | المراقبة والتنبيه

| Event (EN) | الحدث (AR) | Alert | التنبيه | Response Time | وقت الاستجابة |
|------------|-----------|-------|---------|---------------|----------------|
| Failed login (>5 attempts) | فشل تسجيل الدخول (>5 محاولات) | Slack + Email | Slack + بريد | Immediate block | حظر فوري |
| Unauthorized API key usage | استخدام مفتاح API غير مصرّح | PagerDuty | PagerDuty | Immediate revocation | إبطال فوري |
| Unusual data export volume | حجم تصدير بيانات غير اعتيادي | Slack | Slack | Manual review within 1 hour | مراجعة يدوية خلال ساعة |
| Database connection spike | ارتفاع اتصالات قاعدة البيانات | PagerDuty | PagerDuty | Auto-scale + investigation | توسيع تلقائي + تحقيق |

### 6.3 Backup Security | أمان النسخ الاحتياطي

**EN:** Backups are encrypted before leaving the application server. Backup access is restricted to 2 senior engineers. Backup restoration requires dual authorization.
**AR:** تُشفّر النسخ الاحتياطية قبل مغادرة خادم التطبيق. يقتصر الوصول إلى النسخ الاحتياطية على مهندسين أولين. يتطلب استعادة النسخ الاحتياطية تصريحاً مزدوجاً.

## 7. Incident Response | الاستجابة للحوادث

### 7.1 Severity Levels | مستويات الخطورة

| Level (EN) | المستوى (AR) | Definition | التعريف | Response Time | وقت الاستجابة |
|------------|-------------|------------|---------|---------------|----------------|
| SEV-1 | SEV-1 | Confirmed data breach or system compromise | اختراق بيانات مؤكد أو اختراق نظام | 15 minutes | 15 دقيقة |
| SEV-2 | SEV-2 | Suspected breach or critical vulnerability | اختراق مشتبه أو ثغرة حرجة | 1 hour | ساعة |
| SEV-3 | SEV-3 | Security misconfiguration or policy violation | إعداد أمان خاطئ أو انتهاك سياسة | 4 hours | 4 ساعات |
| SEV-4 | SEV-4 | Security finding from routine audit | نتيجة أمان من تدقيق روتيني | 7 days | 7 أيام |

### 7.2 Response Steps | خطوات الاستجابة

**EN:**
1. Detect and classify the incident.
2. Contain: isolate affected systems.
3. Eradicate: remove threat actor access.
4. Recover: restore systems from clean backups.
5. Post-mortem: document root cause and preventive actions.

**AR:**
1. الكشف والتصنيف.
2. الحصر: عزل الأنظمة المتأثرة.
3. القضاء: إزالة وصول الفاعل المهدد.
4. الاستعادة: استعادة الأنظمة من نسخ احتياطية نظيفة.
5. ما بعد الوفاة: توثيق السبب الجذري والإجراءات الوقائية.

### 7.3 Notification | الإشعار

**EN:**
- SEV-1: Notify affected tenants within 24 hours.
- SEV-2: Notify within 48 hours if tenant data is potentially affected.
- All incidents: Internal post-mortem within 72 hours.

**AR:**
- SEV-1: إشعار المستأجرين المتأثرين خلال 24 ساعة.
- SEV-2: إشعار خلال 48 ساعة إذا كانت بيانات المستأجرين محتملة التأثر.
- جميع الحوادث: ما بعد الوفاة الداخلية خلال 72 ساعة.

## 8. Compliance and Audits | الامتثال والتدقيق

| Standard (EN) | المعيار (AR) | Status | الحالة | Target Date | التاريخ المستهدف |
|---------------|-------------|--------|--------|-------------|------------------|
| UAE PDPL | PDPL الإمارات | Compliant | متوافق | Active | نشط |
| PCI DSS | PCI DSS | In progress | قيد التنفيذ | Q4 2026 | Q4 2026 |
| ISO 27001 | ISO 27001 | In progress | قيد التنفيذ | Q1 2027 | Q1 2027 |
| SOC 2 Type II | SOC 2 Type II | Roadmap | خارطة الطريق | Q2 2027 | Q2 2027 |

**EN:** Quarterly internal security audits are conducted by the CTO. Annual third-party penetration tests are mandatory.
**AR:** يُجري CTO تدقيقات أمان داخلية ربع سنوية. اختبارات الاختراق السنوية من طرف ثالث إلزامية.

## 9. Third-Party Security | أمان الأطراف الثالثة

**EN:** All third-party vendors with access to AZAD systems must: sign a Data Processing Agreement (DPA), provide a SOC 2 Type II report or equivalent, undergo annual security questionnaires.
**AR:** يجب على جميع البائعين من الأطراف الثالثة الذين لديهم وصول إلى أنظمة أزاد: توقيع اتفاقية معالجة بيانات (DPA)، تقديم تقرير SOC 2 Type II أو ما يعادله، الخضوع لاستبيانات أمان سنوية.

## 10. Policy Review | مراجعة السياسة

**EN:** This policy is reviewed quarterly. Violations may result in disciplinary action, including termination and legal proceedings.
**AR:** تُراجع هذه السياسة ربع سنوياً. قد تؤدي الانتهاكات إلى إجراءات تأديبية، بما في ذلك الإنهاء والإجراءات القانونية.

## 11. Contact | التواصل

Chief Security Officer (acting): Eng. Ahmad Ghannam | مسؤول الأمان الرئيسي (بالإنابة): م. أحمد غنام
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
