# Azadexa Project Overview

**Azadexa** / **أزاديكسا** is an intelligent multi-tenant ERP, accounting, inventory, and commerce platform by **AZAD Intelligent Systems**.

The platform operates real business workflows. It combines tenant ERP operations, accounting, inventory, tenant-specific commerce, branch operations, platform-owner administration, public package/donation flows, payment vault, monitoring, APIs, and optional AI surfaces in one system.

---

## Product summary

Azadexa is a proprietary business operating platform for organizations that need:

- sales, POS, returns, customer balances, and payment workflows;
- purchases, supplier balances, and payable workflows;
- product catalog, warehouse control, stock movement, serials, warranty, and costing;
- general ledger, journal entries, account mapping, VAT, budgets, assets, and financial dimensions;
- branch-aware permissions and warehouse access;
- tenant-specific stores with public catalog, cart, checkout, coupons, variants, loyalty, and notifications;
- platform-owner package purchases, public donations, vault/payment settings, and owner controls;
- Arabic-first ERP user experience with modern business workflows.

---

## Arabic summary

**أزاديكسا** منصة ERP وتجـارة ومحاسبة ومخزون ذكية متعددة المستأجرين.

هي ليست متجراً واحداً ولا برنامج فواتير بسيطاً؛ بل نظام تشغيل أعمال يسمح لكل مستأجر بإدارة بياناته وعملياته ومحاسبته ومخزونه ومتجره بمعزل عن الآخرين، مع وجود طبقة عليا لمالك المنصة لإدارة الحزم، الدفعات العامة، التبرعات، خزنة الدفع، والتحكمات العامة.

---

## Main actors

| Actor | Description |
|------|-------------|
| Platform owner | Controls owner panel, package purchases, public donations, vault/payment settings, tenant administration, and platform-level policies |
| Tenant admin | Manages company users, branches, warehouses, store settings, and tenant operations |
| Branch user | Works inside tenant branch visibility and assigned permissions |
| Accountant | Manages ledger, payments, cheques, balances, reports, assets, budgets, and financial postings |
| Seller / POS user | Creates sales, POS invoices, receipts, and related inventory effects |
| Warehouse user | Manages stock, transfers, warehouse quantities, and stock adjustments |
| Store visitor/customer | Uses a tenant-specific public store catalog, cart, checkout, account, reviews, loyalty, or order view |
| API/integration actor | Interacts with API, GraphQL, analytics, WhatsApp, monitoring, or AI surfaces under the same boundaries |

---

## Code-derived module families

The repository modules show these major families:

| Family | Included areas |
|--------|----------------|
| Tenant ERP | sales, POS, returns, customers, suppliers, purchases, products, branches, users, roles, permissions |
| Inventory | warehouses, stock movements, product warehouse stock, product serials, warranty claims, stock alerts |
| Costing | product warehouse cost, product cost history, landed unit cost, MWAC/WAC behavior |
| Accounting | GL accounts, journal entries, journal lines, periods, mappings, bank reconciliation, budgets, assets, cost/profit centers, tax rules |
| Payments | payments, receipts, cheques, pending/rejected cheque behavior, cash boxes, treasury |
| Commerce | tenant stores, store payment methods, shop accounts, wishlist, reviews, abandoned carts, saved payments, variants, coupons, loyalty, newsletters, shipments |
| Platform owner | payment vault, card vault, card payments, donations, packages, package purchases, platform fees, owner panel |
| Control surfaces | monitoring, API, enhanced API, analytics API, API docs, GraphQL, WhatsApp, gamification, AI |

See [`SYSTEM_MODULES.md`](SYSTEM_MODULES.md) and [`SYSTEM_FLOWS.md`](SYSTEM_FLOWS.md) for deeper maps.

---

## Business modules

| Module | Purpose |
|--------|---------|
| Sales | sales records, invoices, line items, customer balances, payments, status, returns interaction |
| POS | fast selling workflow with stock and payment impact |
| Purchases | supplier documents, landed costs, stock receipt, supplier payable behavior |
| Products | catalog, categories, pricing tiers, serials, images, warranty, partner shares |
| Inventory | stock movements, warehouse quantities, transfers, adjustments, online warehouse stock |
| Warehouses | physical and online warehouses, branch linkage, stock visibility |
| Accounting | chart of accounts, journal entries, GL lines, account mappings, periods, VAT, reports |
| Customers | customer profiles, classification, statements, balances, shop account linkage |
| Suppliers | supplier profiles, purchase links, balances, payment history |
| Payments and cheques | incoming/outgoing payments, receipts, confirmed/pending/rejected cheque states |
| Branches | branch-aware operations, report scope, warehouse access |
| Tenant stores | one store per tenant, online warehouse, public catalog, cart, checkout, coupons, loyalty |
| Platform owner | owner panel, package purchases, donations, vault, platform payment settings, tenant administration |

---

## Platform boundaries

Azadexa has five important scopes:

1. **Tenant ERP scope** — normal business operations for one tenant/company.
2. **Branch scope** — visibility and operations inside a branch/warehouse boundary.
3. **Tenant store scope** — public commerce tied to one tenant and one online warehouse.
4. **Platform-owner scope** — owner panel, payment vault, donations, package purchases, platform fees, and global controls.
5. **Public scope** — anonymous pages that must expose only safe public information.

These scopes are core system boundaries and must not be mixed accidentally.

---

## Tenant policy

- Each tenant owns its operational records.
- Company users are locked to their own tenant context.
- Platform-owner users may switch active tenant context.
- Tenant data must be isolated in queries, services, routes, templates, reports, APIs, and store flows.
- Tenant stores are tenant-specific and tied to their store identity.
- Public landing, donations, and package purchase flows are platform-owner flows.
- Public platform payments belong to the platform-owner vault unless explicitly designed otherwise.

---

## Accounting expectations

Accounting behavior should prioritize correctness over UI convenience.

A financial workflow should answer:

- Which tenant owns this transaction?
- Which branch is affected?
- Which customer, supplier, account, warehouse, cost center, profit center, or partner is affected?
- Does this change inventory?
- Does this create or reverse a ledger entry?
- Does this affect tenant money or platform-owner money?
- Is the operation traceable through source document, reference type, and audit trail?

---

## System goals

The system documentation and code should support:

- accurate description of actual modules and model families;
- tenant isolation and branch visibility as first-class concepts;
- correct sales, purchase, payment, cheque, return, and balance behavior;
- inventory movement traceability and warehouse-level costing;
- GL posting with balanced entries and clear reference types;
- tenant-store behavior as a tenant-owned commerce layer;
- public donations and package purchases as platform-owner flows;
- clear boundaries for AI, API, GraphQL, monitoring, and integrations;
- Arabic-first business usability and professional ERP wording.

---

## Non-goals

Azadexa should not be described as:

- an Amazon clone;
- a generic open-source ERP template;
- a single-tenant shop;
- a demo-only Flask app;
- a public reusable framework;
- a documentation-only project.

It is a proprietary business platform owned by **AZAD Intelligent Systems**.
