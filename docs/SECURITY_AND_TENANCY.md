# Azadexa Security and Tenancy Guide

This guide defines the security and tenant-isolation rules for **Azadexa**, the intelligent multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

Security in Azadexa is not only login protection. It includes tenant isolation, branch scope, owner-only boundaries, payment ownership, secret handling, and safe production operation.

---

## Core principles

- Tenant isolation is mandatory.
- Platform-owner flows are not tenant flows.
- Tenant stores must remain tenant-scoped.
- Public landing, donation, and package purchase flows belong to platform-owner scope unless explicitly designed otherwise.
- Sensitive card/payment vault actions must remain owner-only.
- No real secrets should ever be committed to Git.
- Debug and bypass flags must never be enabled in production.

---

## Scope model

| Scope | Meaning | Risk if broken |
|------|---------|----------------|
| Tenant scope | Records belonging to one company/tenant | Cross-tenant data leak or financial corruption |
| Branch scope | Records limited to a tenant branch | Users may see or mutate another branch's operations |
| Tenant store scope | Storefront data for a specific tenant | Store orders/products may leak across tenants |
| Platform-owner scope | Owner-level platform operations | Tenant users may access platform money/settings |
| Public scope | Routes for unauthenticated users | Public route may become data exfiltration path |

---

## Tenant isolation rules

Every tenant-owned query must be tenant-aware.

Preferred protections:

1. ORM-level tenant criteria for tenant-owned models.
2. Explicit tenant query helpers in routes and services.
3. `tenant_id` assignment on create/update operations.
4. Branch filters where branch visibility applies.
5. Route-level permissions before data access.
6. QA checks for cross-tenant behavior.

Do not assume that hiding a button or menu item protects data.

---

## Route review checklist

For every route or API endpoint, verify:

- Is this endpoint authenticated, public, or owner-only?
- If authenticated, what permission/role is required?
- If tenant-scoped, how is `tenant_id` enforced?
- If branch-scoped, how is branch visibility enforced?
- If public, does it expose only safe public data?
- If owner-only, does it reject tenant admins?
- Does it decrypt, export, or display sensitive information?
- Does it perform mutation or only read data?
- Is the redirect target safe?
- Are errors logged without leaking secrets?

---

## Owner-only rules

Owner-only functionality includes platform-level controls such as:

- card/payment vault operations;
- platform package purchases;
- public donation revenue;
- platform payment provider callbacks where relevant;
- global tenant administration;
- database/export/maintenance tooling;
- high-level monitoring and diagnostics;
- owner financial vault and treasury flows.

Normal tenant admins must not receive owner permissions by accident.

---

## Payment ownership rules

| Flow | Scope | Notes |
|------|-------|-------|
| Tenant sale payment | Tenant scope | Must affect the tenant's business records only |
| Tenant store checkout | Tenant store scope | Must stay attached to the tenant store/order |
| Public donation | Platform-owner scope | Platform revenue, not tenant revenue |
| Package/subscription purchase | Platform-owner scope | Platform revenue and package activation flow |
| Owner vault/card action | Platform-owner scope | Must remain owner-only |

Payment code must not mix tenant and platform-owner money without a deliberate accounting design.

---

## Secrets policy

Never commit:

- `.env` files with real secrets;
- API keys;
- database passwords;
- encryption keys;
- card data;
- private backups;
- production database dumps;
- provider webhook secrets;
- personal access tokens.

Use placeholders in documentation and examples:

```bash
SECRET_KEY=CHANGE_ME
CARD_ENCRYPTION_KEY=CHANGE_ME
DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME
NOWPAYMENTS_IPN_SECRET=CHANGE_ME
```

---

## Production forbidden settings

Never use these in production:

```bash
DEBUG=true
FLASK_ENV=development
APP_ENV=development
SKIP_SYSTEM_INTEGRITY=1
```

Production should use HTTPS, secure cookies, server-side secrets, and a production database.

---

## Database and export safety

Database tools are high-risk in an ERP platform.

Rules:

- Export tools must hide or block sensitive tables unless explicitly owner-approved.
- SQL console behavior must be read-only in production.
- Destructive tools must not be exposed to tenant users.
- Backups must be stored outside public web paths.
- Backups must not be committed to Git.
- Restore workflows must preserve tenant boundaries.

---

## Logging rules

Logs should help diagnose issues without leaking secrets.

Do log:

- error category;
- route/function name;
- current user id when safe;
- tenant id when safe;
- operation id/source id;
- sanitized provider status.

Do not log:

- card numbers;
- CVV;
- raw payment secrets;
- API keys;
- full database URLs with passwords;
- session cookies;
- access tokens;
- private customer financial data unless masked and necessary.

---

## Public route rules

Public routes may include landing pages, package purchase screens, donations, and limited storefront flows.

Public routes must not:

- list tenants' private data;
- expose internal ids unnecessarily;
- allow arbitrary tenant switching without validation;
- accept payment callbacks without verification;
- redirect to arbitrary external URLs;
- expose owner vault or card data.

---

## Tenant store rules

Tenant stores belong to their tenant.

Store-related code must verify:

- tenant identity;
- product visibility inside tenant scope;
- store settings inside tenant scope;
- order ownership;
- payment ownership;
- stock impact;
- customer/order history isolation.

---

## AI assistant and automation rules

When an AI assistant modifies the project, it must not:

- remove tenant filters casually;
- replace scoped queries with global queries;
- bypass owner-only checks;
- move payment-vault logic into tenant routes without design review;
- change accounting formulas without explaining debit/credit impact;
- modify migrations without checking current database state;
- push secrets or local environment files;
- treat docs as proof that code is safe without verifying code paths.

---

## Security review checklist before release

- Owner-only routes reviewed.
- Tenant-scoped routes reviewed.
- Public routes reviewed.
- Payment webhooks validated.
- Sensitive exports blocked/masked.
- Debug disabled.
- Production secrets are server-only.
- Database backups tested.
- Restore path tested on staging.
- Cross-tenant UAT completed.
- Accounting and inventory side effects reviewed.
