# Security Policy — AZAD Intelligent Systems

## 1. Scope

This policy applies to all employees, contractors, and third-party vendors with access to Azadexa ERP systems, infrastructure, or customer data.

## 2. Security Principles

| Principle | Implementation |
|-----------|----------------|
| Defense in depth | Multiple security layers: network, application, database, physical |
| Least privilege | Users and services receive only the minimum required access |
| Zero trust | No implicit trust based on network location |
| Tenant isolation | Logical and query-level separation of tenant data |
| Audit everything | All access and changes are logged |

## 3. Access Control

### 3.1 Authentication

| Layer | Mechanism |
|-------|-----------|
| Application | Username + password + optional 2FA |
| API | API key + secret (HMAC-signed requests) |
| Owner panel | Separate owner credentials with IP allowlisting |

### 3.2 Password Policy

| Rule | Requirement |
|------|-------------|
| Minimum length | 12 characters |
| Complexity | Upper, lower, digit, special character |
| Rotation | Every 90 days for admin accounts |
| Reuse | Last 5 passwords cannot be reused |
| Storage | Argon2id hashing (never plain text) |

### 3.3 Session Management

- Session timeout: 24 hours idle, 8 hours absolute for sensitive routes.
- Concurrent session limit: 3 per user.
- Session invalidation on password change or suspicious activity.

### 3.4 Role-Based Access Control

| Role | Typical Permissions |
|------|-------------------|
| Owner | Full system access, billing, user management |
| Admin | All modules except billing and owner settings |
| Accountant | GL, payments, cheques, reports |
| Sales Manager | Sales, customers, POS, reports |
| Cashier | POS only, limited to assigned branch |
| Warehouse | Inventory, stock movements, transfers |
| Viewer | Read-only access to assigned modules |

Permissions are enforced via `@permission_required('code')` and verified at the service layer.

## 4. Data Protection

### 4.1 Classification

| Level | Examples | Handling |
|-------|----------|----------|
| Public | Marketing website, pricing page | No restrictions |
| Internal | API docs, system architecture | Share internally only |
| Confidential | Customer lists, revenue data | Encrypted, need-to-know |
| Restricted | Card vault, API secrets, tenant backups | Encryption + MFA + audit |

### 4.2 Encryption

| State | Method | Key Management |
|-------|--------|----------------|
| In transit | TLS 1.3 | Let's Encrypt / Cloudflare |
| At rest (DB) | PostgreSQL TDE | Cloud provider KMS |
| At rest (backups) | AES-256-GCM | HSM-backed keys |
| Card data | Tokenization + AES-256 | PCI-compliant vault |

### 4.3 Tenant Isolation

- Every database query is scoped by `tenant_id` via `tenant_query()`.
- ORM auto-scoping is registered in `utils/tenant_orm.py`.
- Cross-tenant access triggers 404 and logs a security alert.
- Raw SQL must append `tenant_id=<tid>` explicitly.

## 5. Application Security

### 5.1 Input Validation

- All JSON requests use `silent=True` and validate structure.
- All `Decimal` conversions guard against `None`.
- SQL injection is prevented via SQLAlchemy ORM and parameterized queries.
- XSS prevention via Jinja2 auto-escaping and CSP headers.

### 5.2 CSRF Protection

- All state-changing forms include CSRF tokens.
- API endpoints use API key authentication (no CSRF needed).

### 5.3 Dependency Management

- Dependencies are pinned in `requirements.txt` with hashes.
- Monthly automated vulnerability scanning via `safety` and `snyk`.
- Critical patches applied within 48 hours of release.

## 6. Infrastructure Security

### 6.1 Network

- WAF (Web Application Firewall) for all public endpoints.
- DDoS protection via Cloudflare or equivalent.
- Private subnets for databases and internal services.
- VPN required for production access.

### 6.2 Monitoring and Alerting

| Event | Alert | Response Time |
|-------|-------|---------------|
| Failed login (>5 attempts) | Slack + Email | Immediate block |
| Unauthorized API key usage | PagerDuty | Immediate revocation |
| Unusual data export volume | Slack | Manual review within 1 hour |
| Database connection spike | PagerDuty | Auto-scale + investigation |

### 6.3 Backup Security

- Backups are encrypted before leaving the application server.
- Backup access is restricted to 2 senior engineers.
- Backup restoration requires dual authorization.

## 7. Incident Response

### 7.1 Severity Levels

| Level | Definition | Response Time |
|-------|------------|---------------|
| SEV-1 | Confirmed data breach or system compromise | 15 minutes |
| SEV-2 | Suspected breach or critical vulnerability | 1 hour |
| SEV-3 | Security misconfiguration or policy violation | 4 hours |
| SEV-4 | Security finding from routine audit | 7 days |

### 7.2 Response Steps

1. Detect and classify the incident.
2. Contain: isolate affected systems.
3. Eradicate: remove threat actor access.
4. Recover: restore systems from clean backups.
5. Post-mortem: document root cause and preventive actions.

### 7.3 Notification

- SEV-1: Notify affected tenants within 24 hours.
- SEV-2: Notify within 48 hours if tenant data is potentially affected.
- All incidents: Internal post-mortem within 72 hours.

## 8. Compliance and Audits

| Standard | Status | Target Date |
|----------|--------|-------------|
| UAE PDPL | Compliant | Active |
| PCI DSS | In progress | Q4 2026 |
| ISO 27001 | In progress | Q1 2027 |
| SOC 2 Type II | Roadmap | Q2 2027 |

Quarterly internal security audits are conducted by the CTO.
Annual third-party penetration tests are mandatory.

## 9. Third-Party Security

All third-party vendors with access to AZAD systems must:
- Sign a Data Processing Agreement (DPA).
- Provide a SOC 2 Type II report or equivalent.
- Undergo annual security questionnaires.

## 10. Policy Review

This policy is reviewed quarterly. Violations may result in disciplinary action, including termination and legal proceedings.

## 11. Contact

Chief Security Officer (acting): Eng. Ahmad Ghannam
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
