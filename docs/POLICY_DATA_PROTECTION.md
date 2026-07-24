# Data Protection Policy — AZAD Intelligent Systems

## 1. Purpose

This policy defines how AZAD Intelligent Systems collects, processes, stores, and destroys data in compliance with the UAE Personal Data Protection Law (PDPL) and international best practices.

## 2. Data Classification

| Class | Examples | Protection Level |
|-------|----------|------------------|
| Public | Website content, pricing, marketing | Standard |
| Internal | Employee directories, API documentation | Internal access only |
| Confidential | Customer databases, financial reports | Encryption + RBAC |
| Restricted | Card vault, passwords, encryption keys | Encryption + MFA + HSM |

## 3. Data Collection

### 3.1 Lawful Basis

| Basis | Context |
|-------|---------|
| Contract | Processing necessary to deliver Azadexa ERP |
| Legal obligation | Tax records, regulatory reporting |
| Legitimate interest | Fraud detection, platform security |
| Consent | Marketing emails, optional AI features |

### 3.2 Minimization

AZAD collects only the data necessary for the stated purpose. No data is collected for speculative future use.

### 3.3 Tenant Data

The Customer (tenant owner) is the data controller for data entered by their Users. AZAD is the data processor. Both parties are jointly responsible for compliance.

## 4. Data Processing

### 4.1 Tenant Isolation

- Data is logically separated by `tenant_id` in every database table.
- ORM auto-scoping (`utils/tenant_orm.py`) prevents cross-tenant leakage.
- Raw SQL requires explicit `tenant_id` filtering.

### 4.2 Processing Integrity

- Multi-model writes use `atomic_transaction` (`utils/db_safety.py`) to ensure consistency.
- Audit logs (`AuditLog` model) record every create, update, and delete.
- GL postings are immutable once finalized.

### 4.3 Automated Decision-Making

The AI assistant provides recommendations (pricing, stock levels) but does not make autonomous decisions affecting legal or financial outcomes. All AI actions are gated by human confirmation (`confirm_required` in `ActionDispatcher`).

## 5. Data Storage

### 5.1 Primary Storage

| Type | Location | Encryption |
|------|----------|------------|
| Application database | UAE data center | AES-256 at rest |
| File uploads | Object storage (S3-compatible) | Server-side encryption |
| Session data | Redis | In-memory only, no persistence |
| Logs | Encrypted log aggregation | TLS in transit |

### 5.2 Backup Storage

| Backup | Frequency | Retention | Location |
|--------|-----------|-----------|----------|
| Full DB snapshot | Daily | 30 days | Same region |
| Incremental WAL | Continuous | 7 days | Same region |
| Scoped export | Weekly | 90 days | Same region |
| Off-site archive | Monthly | 1 year | Secondary region |

All backups are encrypted with AES-256-GCM using HSM-backed keys.

### 5.3 Data Localization

Tenant data is stored in the UAE by default. If a Customer requests data residency in another jurisdiction, AZAD will assess feasibility on a case-by-case basis.

## 6. Data Retention and Disposal

| Data Type | Retention | Disposal Method |
|-----------|-----------|-----------------|
| Active tenant data | Subscription duration + 30 days | Logical deletion + DB vacuum |
| Deleted tenant data | 90 days after deletion | Cryptographic erasure |
| Audit logs | 2 years | Archive then shred |
| Payment records | 7 years | Archive then shred |
| Error logs | 90 days | Automatic purge |
| Backups | Per backup policy | Secure deletion with verification |

Upon tenant deletion:
1. Data is immediately soft-deleted (hidden from UI).
2. After 30 days, hard-deleted from the active database.
3. After 90 days, purged from all backups and archives.
4. A certificate of destruction is available on request.

## 7. Data Subject Rights

| Right | How to Exercise | SLA |
|-------|-----------------|-----|
| Access | Tenant admin exports data via UI | Immediate |
| Rectification | Edit directly in the application | Immediate |
| Erasure | Request tenant deletion via support | 30 days |
| Portability | Export to JSON or Excel | Immediate |
| Restriction | Contact support to freeze processing | 24 hours |
| Objection | Unsubscribe from marketing emails | Immediate |

Data Subject Access Requests (DSAR) are processed within 30 days of receipt.

## 8. Data Sharing and Transfers

### 8.1 Third Parties

AZAD shares data only with:
- Payment processors (Stripe, NOWPayments) under DPA.
- Cloud infrastructure providers under DPA.
- Law enforcement when legally compelled by valid court order.

### 8.2 International Transfers

If data must leave the UAE:
- Transfer is limited to countries with adequate data protection (EU adequacy decisions).
- Standard Contractual Clauses (SCCs) are used for other jurisdictions.
- Data is encrypted during transfer.

## 9. Data Breach Response

### 9.1 Detection

- Automated monitoring for unusual access patterns.
- Regular penetration testing.
- Employee reporting channel.

### 9.2 Response Timeline

| Phase | Time | Action |
|-------|------|--------|
| Detection | Ongoing | Automated alerts + manual review |
| Containment | 1 hour | Isolate affected systems |
| Assessment | 4 hours | Determine scope and impact |
| Notification | 24 hours | Notify affected tenants and regulator if required |
| Remediation | 72 hours | Patch, rotate credentials, restore systems |
| Post-mortem | 7 days | Root cause analysis + preventive measures |

## 10. Training and Awareness

- Annual data protection training for all employees.
- Role-specific training for developers (tenant isolation, secure coding).
- Quarterly phishing simulations.

## 11. Policy Review

This policy is reviewed annually and whenever there is a significant change in regulations or business operations.

## 12. Contact

Data Protection Officer (acting): Eng. Ahmad Ghannam
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
