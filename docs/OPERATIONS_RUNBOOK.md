# Azadexa System Operating Model

This document describes how **Azadexa** behaves as an internal business system. It is not a deployment guide.

Azadexa is a multi-tenant ERP, accounting, inventory, and commerce platform. Its operating model is built around tenant ownership, branch visibility, financial correctness, stock traceability, tenant storefronts, and platform-owner boundaries.

---

## Operating scopes

Every feature belongs to one of these scopes:

| Scope | Meaning | Examples |
|------|---------|----------|
| Tenant ERP scope | Normal company operations owned by one tenant | sales, purchases, customers, suppliers, warehouses, payments, ledger |
| Branch scope | Operational visibility inside a tenant branch | branch sales, branch reports, warehouse access |
| Tenant store scope | Public commerce for a specific tenant | store catalog, cart, checkout, store orders |
| Platform-owner scope | AZAD/platform-level control | packages, donations, payment vault, tenant administration, owner panel |
| Public scope | Anonymous pages with limited safe behavior | landing pages, package pages, public store catalog |

A change is incomplete until its scope is known.

---

## Core operating loop

A normal tenant business workflow follows this pattern:

```text
user action
  -> permission check
  -> tenant and branch resolution
  -> document creation or update
  -> stock effect when applicable
  -> GL/accounting effect when applicable
  -> balance/status recalculation
  -> report visibility
```

This applies to sales, purchases, payments, returns, stock adjustments, cheque state changes, and accounting operations.

---

## Tenant and branch behavior

Authenticated company users are locked to their own `user.tenant_id`. Platform-owner users may work with a selected active tenant context.

Tenant-owned reads are protected through ORM-level scoping and explicit tenant helpers. Public storefront routes are special: they resolve tenant context from the store slug/domain and must filter by that store tenant.

Branch scope is separate from tenant scope. A branch-aware operation should preserve tenant id, branch id, warehouse id where relevant, user permissions, report branch visibility, and GL line branch dimensions when accounting is posted.

---

## Sales behavior

A sale may affect customer balance, payment status, pending cheque state, return impact, warehouse stock, serial numbers, warranty dates, partner commissions, GL revenue, VAT output, COGS, inventory asset posting, and tenant store order state.

Deferred online orders should not be treated the same as fulfilled POS/internal sales until fulfillment is confirmed.

---

## Purchase behavior

A purchase may affect supplier balance, warehouse stock, product cost, landed cost allocation, MWAC/WAC records, VAT input, payable accounts, stock valuation, and GL posting.

Purchase totals include subtotal, discount, tax, and landed-cost components such as freight, insurance, customs duty, and other landed costs.

---

## Inventory and costing behavior

Inventory is movement-based. Stock operations should create movement records and update warehouse-level quantities.

When MWAC/WAC is enabled, stock valuation is warehouse-level through `ProductWarehouseCost` and `ProductCostHistory`. Landed unit cost from purchase lines feeds product cost and valuation behavior.

---

## Accounting behavior

GL posting is a central system behavior. Financial documents should create balanced journal entries when they have accounting impact.

The system supports tenant chart of accounts, account tree validation, journal entries and lines, period locking, reversing entries, dynamic concept-to-account mapping, VAT reporting, liquidity account resolution, and manual/automatic entries.

---

## Payment and cheque behavior

The system distinguishes incoming and outgoing payments, customer and supplier flows, sale-linked and purchase-linked payments, and confirmed versus pending/rejected cheque states.

Pending cheques should not reduce confirmed balances until cleared. Rejected cheques must trigger recalculation of the affected sale/payment state.

---

## Tenant storefront behavior

Each tenant can have one tenant store. A tenant store has one tenant id, one online warehouse, slug/subdomain/custom-domain identity, enabled state, platform hard-lock option, public catalog, tenant cart, checkout, coupons, loyalty, variants, reviews, saved accounts, and notifications where enabled.

A public store visitor is not a tenant admin. Store routes derive tenant context from store identity, not from the visitor session.

---

## Platform-owner behavior

Platform-owner workflows are separate from tenant business workflows. They include the owner panel, platform payment vault, public donations, package purchases, platform fee concepts, tenant administration, and global controls such as store enablement.

Public donations and package purchases are platform-owner revenue flows unless a documented business rule says otherwise.

---

## Control surfaces

Azadexa also includes AI routes, REST/API endpoints, GraphQL, analytics API, monitoring, WhatsApp integration, gamification, and API documentation.

These surfaces must follow the same tenant, branch, store, owner, and public-scope rules as the rest of the system.

---

## Documentation maintenance rule

When system behavior changes, update the matching system document:

- module/domain change → `SYSTEM_MODULES.md`;
- business scope change → `PROJECT_OVERVIEW.md`;
- tenant/security boundary → `SECURITY_AND_TENANCY.md`;
- accounting/stock/balance rule → `ACCOUNTING_AND_INVENTORY_RULES.md`;
- architecture/service boundary → `ARCHITECTURE.md`;
- product naming/identity → `AZADEXA_BRAND.md`.
