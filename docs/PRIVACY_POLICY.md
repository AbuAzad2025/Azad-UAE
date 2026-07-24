# Privacy Policy — AZAD Intelligent Systems

## 1. Data Controller

AZAD Intelligent Systems ("AZAD", "We", "Us") is the data controller for all personal data processed through the Azadexa ERP platform.

Contact: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193

## 2. Data We Collect

| Category | Data Elements | Purpose |
|----------|---------------|---------|
| Account data | Name, email, phone, company name, tax number | Tenant provisioning, billing, support |
| Usage data | Login history, IP address, user agent, actions performed | Security auditing, fraud detection, product improvement |
| Financial data | Invoices, payments, bank details | Transaction processing, accounting |
| Employee data | Name, salary, attendance, leave | Payroll and HR modules (entered by Customer) |
| Customer/supplier data | Names, contacts, balances | CRM and sales modules (entered by Customer) |
| Technical data | Error logs, performance metrics, API requests | Debugging, monitoring, optimization |
| Cookie data | Session ID, preferences, analytics | Authentication, UX improvement |

## 3. Legal Basis for Processing

| Basis | Application |
|-------|-------------|
| Contract performance | Processing necessary to deliver the Service |
| Legal obligation | Tax reporting, regulatory compliance |
| Legitimate interest | Security, fraud prevention, analytics |
| Consent | Marketing communications, optional features |

## 4. How We Use Data

4.1 To provide, maintain, and improve the Service.

4.2 To process billing and payments.

4.3 To send transactional notifications (invoices, alerts, security events).

4.4 To provide customer support.

4.5 To comply with legal obligations (tax, audit, law enforcement requests).

4.6 For internal analytics and product development.

## 5. Data Sharing

5.1 We do not sell personal data to third parties.

5.2 We share data only with:
- Payment processors (Stripe, NOWPayments) for transaction processing.
- Cloud infrastructure providers (hosting, CDN) under strict confidentiality.
- Law enforcement when legally compelled by a valid court order.

5.3 All third-party processors are bound by Data Processing Agreements (DPA) with confidentiality and security obligations.

## 6. Data Retention

| Data Type | Retention Period |
|-----------|------------------|
| Active Tenant data | Duration of subscription + 30 days export window |
| Deleted Tenant data | 90 days after deletion, then secure erasure |
| Audit logs | 2 years |
| Payment records | 7 years (tax compliance) |
| Error logs | 90 days |
| Backup archives | Up to 1 year, encrypted and isolated |

## 7. Security Measures

7.1 Encryption: TLS 1.3 for data in transit; AES-256 for backups at rest.

7.2 Tenant isolation: Each Tenant's data is logically separated by `tenant_id` and enforced at the ORM and database query levels.

7.3 Access control: Role-based permissions (`Role`, `Permission` models) with audit logging.

7.4 Incident response: 24-hour notification for confirmed breaches affecting personal data.

## 8. Customer Rights

The Customer (as data controller for its Users) and end-users (where applicable) have the right to:

| Right | How to Exercise |
|-------|-----------------|
| Access | Request an export of all Data associated with the Tenant |
| Rectification | Update Data directly within the Service |
| Erasure | Request Tenant deletion; Data is purged after the retention period |
| Restriction | Contact AZAD support to temporarily restrict processing |
| Portability | Export Data in JSON or Excel format |
| Objection | Contact AZAD to object to non-essential processing |

Requests are processed within 30 days.

## 9. Cookies and Tracking

| Cookie | Purpose | Duration |
|--------|---------|----------|
| session | Authentication | Session |
| csrf_token | CSRF protection | Session |
| locale | Language preference | 1 year |
| analytics | Usage analytics | 90 days |

Users may disable non-essential cookies via browser settings. Essential cookies (session, csrf) cannot be disabled.

## 10. International Transfers

Data is hosted in the UAE. If backup or disaster recovery requires transfer to another jurisdiction, we ensure:
- Adequate protection standards (EU adequacy decisions or SCCs).
- Encryption during transfer.
- Limitation to jurisdictions with strong data protection laws.

## 11. Children's Privacy

The Service is not intended for individuals under 18. We do not knowingly collect data from minors.

## 12. Changes to This Policy

We may update this Privacy Policy with 30 days notice. Continued use constitutes acceptance.

## 13. Contact

For privacy inquiries or Data Subject Access Requests (DSAR):
- Email: rafideen.ahmadghannam@gmail.com
- Phone: +972 56 215 0193
