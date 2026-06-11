# Azadexa Architecture

This document describes the high-level architecture of **Azadexa**, the intelligent multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

---

## Architecture goals

Azadexa must support:

- clear tenant isolation;
- reliable ERP workflows;
- correct accounting and inventory behavior;
- owner-only platform controls;
- Arabic-first business UI;
- safe production deployment;
- maintainable code organization;
- predictable service boundaries.

---

## System style

Azadexa is a Flask-based web application with a layered structure:

```text
HTTP request
  -> Flask route / blueprint
  -> decorators and permission checks
  -> tenant resolution and scoping
  -> service layer
  -> SQLAlchemy models
  -> database
  -> template / JSON response
```

The application should avoid putting complex business rules directly in templates or route handlers when those rules belong in reusable services.

---

## Main layers

| Layer | Purpose |
|------|---------|
| `routes/` | HTTP endpoints, page rendering, request validation, permission gates |
| `services/` | business rules, accounting logic, inventory logic, reporting logic |
| `models/` | SQLAlchemy tables and relationships |
| `utils/` | shared helpers, tenant utilities, decorators, safety helpers |
| `templates/` | Jinja2 user interface |
| `static/` | JavaScript, CSS, images, frontend behavior |
| `migrations/` | Alembic schema evolution |
| `runtime_core/` | startup integrity and idempotent repairs |
| `tools/` | development, audit, QA, and maintenance scripts |

---

## Request handling principles

Every route should answer these questions before reading or mutating data:

1. Is the user authenticated?
2. What role/permission is required?
3. Is this route tenant-scoped, platform-scoped, or public?
4. What is the active tenant?
5. Is branch scoping required?
6. Is the query protected by tenant filters or tenant helpers?
7. Does the operation affect inventory, accounting, payments, or owner vault data?
8. Is the operation auditable?

---

## Tenant architecture

Azadexa uses a multi-layer tenant isolation model.

Expected isolation layers:

- tenant-aware database models where applicable;
- ORM-level filtering for tenant-owned models;
- explicit tenant query helpers in route and service code;
- branch scope checks where relevant;
- permission checks on route entry;
- tests and QA scripts for cross-tenant behavior;
- conservative defaults for public and owner-only flows.

Tenant isolation should not rely only on UI filtering.

---

## Scope types

| Scope | Description | Examples |
|------|-------------|----------|
| Tenant scope | Business data belonging to one tenant | sales, purchases, inventory, customers, suppliers, tenant accounting |
| Branch scope | Sub-scope inside a tenant | branch-specific sales, stock, users, reports |
| Tenant store scope | Storefront and commerce data for one tenant | tenant products, store checkout, tenant orders |
| Platform-owner scope | System owner operations | packages, public payments, owner vault, platform settings |
| Public scope | Routes accessible without tenant login | landing pages, public package pages, donation pages |

Public scope must not become an accidental data access bypass.

---

## Accounting architecture

Accounting workflows should be handled through services rather than scattered route calculations.

A financial operation should define:

- tenant id;
- branch id where relevant;
- affected account(s);
- debit and credit sides;
- source document type and id;
- currency and amount;
- posting date;
- reversal/void policy;
- audit trail.

Do not update balances in one place while ledger entries are created somewhere else without a clear consistency rule.

---

## Inventory architecture

Inventory operations should be traceable through movement records.

A stock-changing operation should define:

- tenant id;
- product id;
- warehouse id;
- quantity change;
- source document;
- date/time;
- user/action responsible;
- whether the movement is reversible;
- whether accounting should also be posted.

Avoid direct stock edits that bypass movement tracking except for controlled administrative corrections.

---

## Payment architecture

Payments must be classified by business owner:

| Payment type | Owner |
|-------------|-------|
| Tenant invoice/store payment | Tenant scope |
| Public donation | Platform-owner scope |
| Package/subscription purchase | Platform-owner scope |
| Owner vault/card operation | Platform-owner scope only |

Payment callbacks/webhooks must validate provider signatures/secrets where available, avoid logging sensitive data, and avoid changing tenant or owner balances without a clear source document.

---

## Owner architecture

Owner functionality must remain isolated from tenant administration.

Owner-only features may include:

- platform settings;
- package/subscription workflows;
- public payment tracking;
- owner vault/payment management;
- global diagnostics and maintenance;
- tenant administration;
- deployment and data tools when explicitly secured.

Owner-only does not mean normal tenant admin.

---

## Frontend architecture

The UI is Arabic-first and RTL-oriented. Frontend changes should preserve:

- RTL layout correctness;
- clear Arabic business wording;
- professional ERP tone;
- responsive tables and dashboards;
- form validation;
- accessibility improvements;
- print/export behavior;
- tenant-specific branding where applicable.

Avoid adding beginner hints, exaggerated language, emoji-heavy status UI, or inconsistent colors in production screens.

---

## Service boundaries

Prefer services for:

- accounting calculations;
- inventory movement logic;
- payment state transitions;
- export/report assembly;
- monitoring and owner dashboards;
- tenant bootstrap and integrity checks;
- reusable validation logic.

Routes should be thin when possible: validate request, enforce permissions, call service, return response.

---

## Data safety rules

- No raw cross-tenant queries unless explicitly platform-owner and safe.
- No production secrets in repository files.
- No unprotected owner/payment/vault endpoints.
- No destructive database tools without strict permission and whitelisting.
- No public route should expose tenant data.
- No direct SQL console behavior should allow mutation in production.

---

## Change review checklist

Before merging architecture-sensitive changes, verify:

- tenant id is applied correctly;
- branch scope is preserved;
- permissions are checked at route level;
- accounting side effects are correct;
- inventory side effects are correct;
- payment ownership is clear;
- templates do not expose unauthorized data;
- migrations are safe;
- tests or manual QA cover the changed path.
