# Compliance Roadmap — AZAD Intelligent Systems

## 1. Current Compliance Status

| Standard | Jurisdiction | Status | Last Review |
|----------|--------------|--------|-------------|
| UAE PDPL (Personal Data Protection Law) | UAE | Compliant | Q2 2026 |
| UAE VAT (Federal Tax Authority) | UAE | Compliant | Q2 2026 |
| UAE E-invoicing (ZATCA-like QR) | UAE | Compliant | Q2 2026 |
| Tenant isolation (logical separation) | Global | Compliant | Ongoing |
| TLS 1.3 encryption | Global | Compliant | Ongoing |
| Role-based access control (RBAC) | Global | Compliant | Ongoing |

## 2. In Progress

| Standard | Target Date | Owner | Status |
|----------|-------------|-------|--------|
| PCI DSS Level 1 | Q4 2026 | CTO | SAQ D in progress |
| ISO 27001:2022 | Q1 2027 | Security Officer | Gap analysis complete |
| SOC 2 Type II | Q2 2027 | CFO + CTO | Roadmap defined |

## 3. Roadmap

### 3.1 PCI DSS Level 1 (Q4 2026)

| Requirement | Implementation |
|-------------|----------------|
| Secure network | WAF, private subnets, VPN |
| Cardholder data protection | AES-256 tokenization in `CardVault` |
| Vulnerability management | Monthly scans, dependency audit |
| Access control | RBAC + MFA + audit logs |
| Monitoring | Real-time alerting, log retention |
| Security policy | `docs/POLICY_SECURITY.md` |

### 3.2 ISO 27001:2022 (Q1 2027)

| Annex A Control | Status |
|-----------------|--------|
| A.5 Information security policies | Draft complete |
| A.6 Organization of information security | `ORG_CHART.md` defines roles |
| A.7 Human resource security | `ONBOARDING.md`, `HANDBOOK.md` |
| A.8 Asset management | Inventory in `static/assets/` |
| A.9 Access control | RBAC implemented |
| A.10 Cryptography | TLS 1.3, AES-256 |
| A.11 Physical security | Cloud provider responsibility |
| A.12 Operations security | `DEPLOYMENT_GUIDE.md` |
| A.13 Communications security | TLS, VPN |
| A.14 System acquisition and maintenance | GRIMOIRE enforces standards |
| A.15 Supplier relationships | DPA with all vendors |
| A.16 Information security incident management | Incident response plan in `POLICY_SECURITY.md` |
| A.17 Business continuity | Backup and DR in `DEPLOYMENT_GUIDE.md` |
| A.18 Compliance | This document |

### 3.3 SOC 2 Type II (Q2 2027)

| Trust Service Criteria | Evidence |
|------------------------|----------|
| Security | `POLICY_SECURITY.md`, access logs, pen test reports |
| Availability | SLA, uptime monitoring, backup tests |
| Confidentiality | Data classification, encryption, DPA |
| Privacy | `PRIVACY_POLICY.md`, DSAR process |

## 4. Regulatory Expansion

| Market | Regulation | Target | Action |
|--------|------------|--------|--------|
| Saudi Arabia | ZATCA e-invoicing | Q1 2027 | Adapt QR code and invoice format |
| Saudi Arabia | Saudi PDPL | Q2 2027 | Update privacy policy and consent flows |
| Egypt | ETA e-invoicing | Q3 2027 | Research and adapt |
| EU | GDPR | On request | Standard Contractual Clauses + DPO |

## 5. Audit Schedule

| Audit | Frequency | Scope | Auditor |
|-------|-----------|-------|---------|
| Internal security audit | Quarterly | RBAC, tenant isolation, access logs | CTO |
| Penetration test | Annual | External + internal network | Third-party |
| Vulnerability scan | Monthly | Dependencies, infrastructure | Automated (Snyk) |
| Compliance review | Quarterly | PDPL, VAT, e-invoice | Internal |
| PCI DSS scan | Quarterly | Card data environment | Approved scanning vendor |

## 6. Incident Reporting

| Authority | Requirement | AZAD Action |
|-----------|-------------|-------------|
| UAE PDPL Authority | Breach notification within 72 hours | 24-hour internal notification; 48-hour authority notification |
| UAE FTA | VAT record retention 5 years | 7-year retention in system |
| PCI SSC | Breach notification within 72 hours | 24-hour notification to acquirer and PCI SSC |

## 7. Training and Certification

| Training | Audience | Frequency | Evidence |
|----------|----------|-----------|----------|
| Security awareness | All employees | Annual | Attendance record |
| PDPL compliance | All employees | Annual | Quiz completion |
| Secure coding | Engineers | Quarterly | `GRIMOIRE.md` enforcement |
| Incident response | Security team | Semi-annual | Drill report |

## 8. Documentation

All compliance documentation is stored in `docs/`:
- `POLICY_SECURITY.md`
- `POLICY_DATA_PROTECTION.md`
- `PRIVACY_POLICY.md`
- `TERMS_OF_SERVICE.md`
- `SLA.md`
- `MASTER_SERVICE_AGREEMENT.md`

## 9. Contact

AZAD Intelligent Systems
Compliance Officer (acting): Eng. Ahmad Ghannam
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
