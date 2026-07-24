# Compliance Roadmap | خارطة طريق الامتثال

## 1. Current Compliance Status | حالة الامتثال الحالية

| Standard (EN) | المعيار (AR) | Jurisdiction | الولاية القضائية | Status | الحالة | Last Review | آخر مراجعة |
|---------------|-------------|--------------|-------------------|--------|--------|-------------|------------|
| UAE PDPL (Personal Data Protection Law) | PDPL الإمارات | UAE | الإمارات | Compliant | متوافق | Q2 2026 | Q2 2026 |
| UAE VAT (Federal Tax Authority) | VAT الإمارات | UAE | الإمارات | Compliant | متوافق | Q2 2026 | Q2 2026 |
| UAE E-invoicing (ZATCA-like QR) | الفاتورة الإلكترونية الإمارات (QR شبيه ZATCA) | UAE | الإمارات | Compliant | متوافق | Q2 2026 | Q2 2026 |
| Tenant isolation (logical separation) | عزل المستأجرين (الفصل المنطقي) | Global | عالمي | Compliant | متوافق | Ongoing | مستمر |
| TLS 1.3 encryption | تشفير TLS 1.3 | Global | عالمي | Compliant | متوافق | Ongoing | مستمر |
| Role-based access control (RBAC) | التحكم بالوصول المعتمد على الأدوار (RBAC) | Global | عالمي | Compliant | متوافق | Ongoing | مستمر |

## 2. In Progress | قيد التنفيذ

| Standard (EN) | المعيار (AR) | Target Date | التاريخ المستهدف | Owner | المالك | Status | الحالة |
|---------------|-------------|-------------|-------------------|-------|--------|--------|--------|
| PCI DSS Level 1 | PCI DSS Level 1 | Q4 2026 | Q4 2026 | CTO | CTO | SAQ D in progress | SAQ D قيد التنفيذ |
| ISO 27001:2022 | ISO 27001:2022 | Q1 2027 | Q1 2027 | Security Officer | مسؤول الأمان | Gap analysis complete | تحليل الفجوة مكتمل |
| SOC 2 Type II | SOC 2 Type II | Q2 2027 | Q2 2027 | CFO + CTO | CFO + CTO | Roadmap defined | خارطة الطريق مُحددة |

## 3. Roadmap | خارطة الطريق

### 3.1 PCI DSS Level 1 (Q4 2026)

| Requirement (EN) | المتطلب (AR) | Implementation | التنفيذ |
|------------------|-------------|----------------|---------|
| Secure network | شبكة آمنة | WAF, private subnets, VPN | WAF، شبكات فرعية خاصة، VPN |
| Cardholder data protection | حماية بيانات حامل البطاقة | AES-256 tokenization in `CardVault` | Tokenization AES-256 في `CardVault` |
| Vulnerability management | إدارة الثغرات | Monthly scans, dependency audit | فحوصات شهرية، تدقيق الاعتماديات |
| Access control | التحكم بالوصول | RBAC + MFA + audit logs | RBAC + MFA + سجلات التدقيق |
| Monitoring | المراقبة | Real-time alerting, log retention | تنبيه لحظي، الاحتفاظ بالسجلات |
| Security policy | سياسة الأمان | `docs/POLICY_SECURITY.md` | `docs/POLICY_SECURITY.md` |

### 3.2 ISO 27001:2022 (Q1 2027)

| Annex A Control (EN) | ضبط Annex A (AR) | Status | الحالة |
|----------------------|-------------------|--------|--------|
| A.5 Information security policies | سياسات أمان المعلومات | Draft complete | المسودة مكتملة |
| A.6 Organization of information security | تنظيم أمان المعلومات | `ORG_CHART.md` defines roles | `ORG_CHART.md` يحدد الأدوار |
| A.7 Human resource security | أمان الموارد البشرية | `ONBOARDING.md`, `HANDBOOK.md` | `ONBOARDING.md`، `HANDBOOK.md` |
| A.8 Asset management | إدارة الأصول | Inventory in `static/assets/` | الجرد في `static/assets/` |
| A.9 Access control | التحكم بالوصول | RBAC implemented | RBAC مُنفّذ |
| A.10 Cryptography | التشفير | TLS 1.3, AES-256 | TLS 1.3، AES-256 |
| A.11 Physical security | الأمان الفيزيائي | Cloud provider responsibility | مسؤولية مزود السحابة |
| A.12 Operations security | أمان العمليات | `DEPLOYMENT_GUIDE.md` | `DEPLOYMENT_GUIDE.md` |
| A.13 Communications security | أمان الاتصالات | TLS, VPN | TLS، VPN |
| A.14 System acquisition and maintenance | اكتساب وصيانة النظام | GRIMOIRE enforces standards | GRIMOIRE يُنفّذ المعايير |
| A.15 Supplier relationships | علاقات الموردين | DPA with all vendors | DPA مع جميع البائعين |
| A.16 Information security incident management | إدارة حوادث أمان المعلومات | Incident response plan in `POLICY_SECURITY.md` | خطة الاستجابة للحوادث في `POLICY_SECURITY.md` |
| A.17 Business continuity | استمرارية الأعمال | Backup and DR in `DEPLOYMENT_GUIDE.md` | النسخ الاحتياطي والDR في `DEPLOYMENT_GUIDE.md` |
| A.18 Compliance | الامتثال | This document | هذا المستند |

### 3.3 SOC 2 Type II (Q2 2027)

| Trust Service Criteria (EN) | معيار خدمة الثقة (AR) | Evidence | الدليل |
|-----------------------------|------------------------|----------|--------|
| Security | الأمان | `POLICY_SECURITY.md`, access logs, pen test reports | `POLICY_SECURITY.md`، سجلات الوصول، تقارير اختبار الاختراق |
| Availability | التوفر | SLA, uptime monitoring, backup tests | SLA، مراقبة التشغيل، اختبارات النسخ الاحتياطي |
| Confidentiality | السرية | Data classification, encryption, DPA | تصنيف البيانات، التشفير، DPA |
| Privacy | الخصوصية | `PRIVACY_POLICY.md`, DSAR process | `PRIVACY_POLICY.md`، عملية DSAR |

## 4. Regulatory Expansion | التوسع التنظيمي

| Market (EN) | السوق (AR) | Regulation | اللائحة | Target | الهدف | Action | الإجراء |
|-------------|-----------|------------|--------|--------|--------|--------|---------|
| Saudi Arabia | السعودية | ZATCA e-invoicing | ZATCA e-invoicing | Q1 2027 | Q1 2027 | Adapt QR code and invoice format | تكييف QR Code وتنسيق الفاتورة |
| Saudi Arabia | السعودية | Saudi PDPL | Saudi PDPL | Q2 2027 | Q2 2027 | Update privacy policy and consent flows | تحديث سياسة الخصوصية وتدفقات الموافقة |
| Egypt | مصر | ETA e-invoicing | ETA e-invoicing | Q3 2027 | Q3 2027 | Research and adapt | البحث والتكييف |

## 5. Audit Schedule | جدول التدقيق

| Audit (EN) | التدقيق (AR) | Frequency | التكرار | Scope | النطاق | Auditor | المُدقق |
|------------|-------------|-----------|---------|-------|--------|---------|--------|
| Internal security audit | تدقيق أمان داخلي | Quarterly | ربع سنوي | RBAC, tenant isolation, access logs | RBAC، عزل المستأجرين، سجلات الوصول | CTO | CTO |
| Penetration test | اختبار اختراق | Annual | سنوي | External + internal network | شبكة خارجية + داخلية | Third-party | طرف ثالث |
| Vulnerability scan | فحص الثغرات | Monthly | شهري | Dependencies, infrastructure | الاعتماديات، البنية التحتية | Automated (Snyk) | آلي (Snyk) |
| Compliance review | مراجعة الامتثال | Quarterly | ربع سنوي | PDPL, VAT, e-invoice | PDPL، VAT، الفاتورة الإلكترونية | Internal | داخلي |
| PCI DSS scan | فحص PCI DSS | Quarterly | ربع سنوي | Card data environment | بيئة بيانات البطاقة | Approved scanning vendor | بائع فحص مُعتمد |

## 6. Incident Reporting | الإبلاغ عن الحوادث

| Authority (EN) | الهيئة (AR) | Requirement | المتطلب | AZAD Action | إجراء أزاد |
|----------------|-------------|-------------|----------|-------------|------------|
| UAE PDPL Authority | هيئة PDPL الإمارات | Breach notification within 72 hours | إشعار الاختراق خلال 72 ساعة | 24-hour internal notification; 48-hour authority notification | إشعار داخلي خلال 24 ساعة؛ إشعار الهيئة خلال 48 ساعة |
| UAE FTA | FTA الإمارات | VAT record retention 5 years | الاحتفاظ بسجلات VAT 5 سنوات | 7-year retention in system | 7 سنوات احتفاظ في النظام |
| PCI SSC | PCI SSC | Breach notification within 72 hours | إشعار الاختراق خلال 72 ساعة | 24-hour notification to acquirer and PCI SSC | إشعار خلال 24 ساعة للمشتري و PCI SSC |

## 7. Training and Certification | التدريب والشهادات

| Training (EN) | التدريب (AR) | Audience | الجمهور | Frequency | التكرار | Evidence | الدليل |
|---------------|-------------|----------|---------|-----------|---------|----------|--------|
| Data protection awareness | التوعية بحماية البيانات | All employees | جميع الموظفين | Annual | سنوي | Attendance record | سجل الحضور |
| PDPL compliance | الامتثال لـ PDPL | All employees | جميع الموظفين | Annual | سنوي | Quiz completion | إتمام الاختبار |
| Secure coding | البرمجة الآمنة | Engineers | المهندسون | Quarterly | ربع سنوي | `GRIMOIRE.md` enforcement | إنفاذ `GRIMOIRE.md` |
| Incident response | الاستجابة للحوادث | Security team | فريق الأمان | Semi-annual | نصف سنوي | Drill report | تقرير التمرين |

## 8. Documentation | المستندات

**EN:** All compliance documentation is stored in `docs/`: `POLICY_SECURITY.md`, `POLICY_DATA_PROTECTION.md`, `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, `SLA.md`, `MASTER_SERVICE_AGREEMENT.md`.
**AR:** جميع مستندات الامتثال مخزنة في `docs/`: `POLICY_SECURITY.md`، `POLICY_DATA_PROTECTION.md`، `PRIVACY_POLICY.md`، `TERMS_OF_SERVICE.md`، `SLA.md`، `MASTER_SERVICE_AGREEMENT.md`.

## 9. Contact | التواصل

Compliance Officer (acting): Eng. Ahmad Ghannam | مسؤول الامتثال (بالإنابة): م. أحمد غنام
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
