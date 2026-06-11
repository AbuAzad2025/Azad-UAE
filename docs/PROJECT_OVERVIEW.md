# Azadexa Project Overview

**Azadexa** / **أزاديكسا** is an intelligent multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

The platform is intended to operate real business workflows, not only display products or run a simple online shop. It combines ERP, accounting, inventory, tenant-specific commerce, branch operations, and platform-owner administration in one system.

---

## Product summary

Azadexa is a proprietary SaaS platform for businesses that need:

- sales and purchases management;
- inventory and warehouse control;
- customer and supplier balances;
- accounting and ledger workflows;
- branch-aware permissions;
- tenant-specific stores;
- platform-owner payment and package flows;
- Arabic-first ERP user experience with support for modern business workflows.

---

## Arabic summary

**أزاديكسا** منصة ERP وتجـارة ذكية متعددة المستأجرين لإدارة الشركات، الفروع، المبيعات، المشتريات، المخزون، المحاسبة، العملاء، الموردين، المستودعات، المتاجر، المدفوعات، وعمليات مالك المنصة.

المنصة ليست متجراً واحداً فقط؛ بل نظام تشغيل أعمال يسمح لكل مستأجر بإدارة بياناته وعملياته ومتجره بمعزل عن المستأجرين الآخرين، مع وجود لوحة عليا لمالك المنصة.

---

## Main actors

| Actor | Description |
|------|-------------|
| Platform owner | The system owner who controls platform-level settings, packages, public payments, and owner-only operations |
| Tenant admin | A company/tenant administrator who manages users, branches, warehouse data, store settings, and operations inside the tenant scope |
| Branch user | A user working inside a tenant branch according to assigned permissions |
| Accountant | A user focused on ledger, payments, balances, reports, invoices, and financial workflows |
| Store/customer user | A storefront visitor or customer interacting with tenant store or public landing flows, depending on route scope |

---

## Business modules

| Module | Purpose |
|--------|---------|
| Sales | sales records, invoices, line items, customer balances, payment links |
| Purchases | purchase records, supplier balances, inventory effects |
| Products | product catalog, categories, stock units, pricing data |
| Inventory | stock movements, warehouse quantities, product availability |
| Warehouses | warehouse-level control and movement records |
| Accounting | chart of accounts, journal entries, general ledger, reports |
| Customers | customer profiles, transaction history, statements, balances |
| Suppliers | supplier profiles, purchase links, balances |
| Payments | operational payments plus platform-owner payment vault boundaries |
| Branches | branch-aware visibility and permissions |
| Users and roles | authentication, authorization, role-based access |
| Tenant stores | per-tenant commerce storefronts and store management |
| Platform owner | owner-only vault, subscriptions/packages, public revenue flows, high-level controls |

---

## Platform boundaries

Azadexa has three important scopes:

1. **Tenant scope** — normal business operations for a specific tenant/company.
2. **Tenant store scope** — store and commerce operations that belong to one tenant.
3. **Platform-owner scope** — public landing pages, donations, package purchases, owner vault, and system-owner administration.

These scopes must not be mixed accidentally.

---

## Tenant policy

- Each tenant owns its operational records.
- Tenant data must be isolated in queries, services, routes, and templates.
- Tenant stores are tenant-specific.
- Public landing, donations, and package purchase flows are platform-level flows.
- Platform public payments belong to the platform-owner treasury/vault unless explicitly designed otherwise.

---

## Accounting expectations

Accounting behavior should prioritize correctness over UI convenience.

A financial workflow should answer:

- Which tenant owns this transaction?
- Which branch is affected?
- Which customer/supplier/account is affected?
- Does this change inventory?
- Does this create a ledger entry?
- Does this affect tenant money or platform-owner money?
- Is the operation reversible or auditable?

---

## Production goal

The project should be treated as a production-bound proprietary ERP platform. Documentation, code, migrations, tests, and deployment procedures should support:

- safe deployment;
- reliable rollback/backup planning;
- tenant isolation;
- secure owner-only workflows;
- clear development onboarding;
- Arabic-first business usability;
- stable accounting and inventory behavior.

---

## Non-goals

Azadexa should not be described as:

- an Amazon clone;
- a generic open-source ERP template;
- a single-tenant shop;
- a demo-only Flask app;
- a public reusable framework.

It is a proprietary business platform owned by **AZAD Intelligent Systems**.
