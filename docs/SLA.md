# Service Level Agreement (SLA) — AZAD Intelligent Systems

## 1. Service Commitment

AZAD Intelligent Systems commits to the following service levels for the Azadexa ERP SaaS platform.

| Metric | Target | Measurement Period |
|--------|--------|---------------------|
| Uptime | 99.9% | Calendar month |
| API availability | 99.95% | Calendar month |
| Data durability | 99.99% | Annual |

Uptime is calculated as: `(Total minutes in month - Downtime minutes) / Total minutes in month * 100`.

Excluded from downtime:
- Scheduled maintenance windows (announced 72 hours in advance).
- Force majeure (natural disasters, internet backbone failures, acts of war).
- Third-party service failures outside AZAD's control (payment gateways, SMS providers).
- Customer-caused issues (misconfiguration, network restrictions on Customer side).

## 2. Scheduled Maintenance

| Type | Frequency | Notice | Duration |
|------|-----------|--------|----------|
| Routine | Weekly | 72 hours | Up to 2 hours |
| Major release | Quarterly | 7 days | Up to 4 hours |
| Emergency patch | As needed | 4 hours | Up to 1 hour |

All maintenance is conducted during the low-usage window: 02:00–06:00 GST (UTC+4).

## 3. Support Response Times

| Severity | Definition | Initial Response | Resolution Target | Communication Channel |
|----------|------------|------------------|-------------------|----------------------|
| P1 — Critical | Service completely unavailable; data loss risk | 15 minutes | 4 hours | Phone + Email + WhatsApp |
| P2 — High | Major feature unusable; significant business impact | 1 hour | 8 hours | Email + WhatsApp |
| P3 — Medium | Partial feature degradation; workaround exists | 4 hours | 48 hours | Email + Ticket |
| P4 — Low | Cosmetic issue; question; enhancement request | 24 hours | 7 days | Ticket |

Response time is measured from the moment AZAD acknowledges the ticket.

## 4. Support Hours

| Channel | Hours | Days |
|---------|-------|------|
| Phone / WhatsApp | 08:00–20:00 GST | Sunday–Thursday |
| Email / Ticket | 24/7 | All days |

P1 issues receive 24/7 response regardless of channel.

## 5. Service Credits

If AZAD fails to meet the monthly uptime target, the Customer is entitled to service credits applied to the next billing cycle:

| Uptime Miss | Credit |
|-------------|--------|
| < 99.9% but ≥ 99.0% | 5% of monthly fee |
| < 99.0% but ≥ 95.0% | 15% of monthly fee |
| < 95.0% | 50% of monthly fee |

Credits are the sole and exclusive remedy for SLA failures. Credits do not exceed 100% of one monthly fee.

To claim credits, the Customer must submit a request within 15 days of the missed month with documented evidence.

## 6. Data Backup and Recovery

| Backup Type | Frequency | Retention | RPO | RTO |
|-------------|-----------|-----------|-----|-----|
| Database snapshot | Daily | 30 days | 24 hours | 4 hours |
| Incremental WAL | Continuous | 7 days | Near-zero | 2 hours |
| Full scoped export | Weekly | 90 days | 7 days | 8 hours |
| Off-site archive | Monthly | 1 year | 30 days | 24 hours |

All backups are encrypted with AES-256 and stored in geographically separate locations.

## 7. Security Incidents

| Incident Type | Notification Time | Action |
|---------------|-------------------|--------|
| Confirmed data breach | Within 24 hours | Email + phone to Customer admin |
| Suspected breach | Within 4 hours | Ticket + monitoring escalation |
| Platform-wide vulnerability | Within 2 hours | In-app banner + email to all admins |

## 8. Performance Benchmarks

| Endpoint | p95 Response Time |
|----------|-------------------|
| Dashboard load | < 800 ms |
| Sale creation | < 1.5 s |
| POS checkout | < 2 s |
| Report generation | < 5 s |
| API response (stock sync) | < 500 ms |
| AI chat response | < 3 s |

## 9. Escalation Path

| Level | Role | Contact |
|-------|------|---------|
| L1 | Support Engineer | support@azadsystems.com |
| L2 | Senior Engineer | senior@azadsystems.com |
| L3 | CTO / Product Lead | cto@azadsystems.com |
| Executive | CEO | rafideen.ahmadghannam@gmail.com |

Escalation from L1 to L2 occurs automatically if a P1 or P2 ticket is unresolved within 50% of the target resolution time.

## 10. SLA Exclusions

The SLA does not apply to:
- Beta, trial, or demo Tenants.
- Features marked as "Experimental" or "Beta" in the UI.
- Performance degradation caused by Customer actions (e.g., importing 1M rows in one batch).
- Failures of Customer-managed integrations (custom webhooks, external APIs).

## 11. Review and Changes

This SLA is reviewed quarterly. Changes are communicated 30 days in advance.

## 12. Contact

AZAD Intelligent Systems
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
