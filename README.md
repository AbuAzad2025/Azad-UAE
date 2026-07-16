# Azadexa

![CI](https://github.com/AbuAzad2025/Azad-UAE/actions/workflows/ci.yml/badge.svg)

**Azadexa** / **أزاديكسا** is an intelligent **multi-tenant ERP, accounting, inventory, and commerce platform** by **AZAD Intelligent Systems**.

This repository represents a real business operating system. It is not a single online store, a demo Flask app, or a generic accounting template. The codebase includes tenant ERP operations, branch-aware workflows, inventory, general ledger accounting, tenant storefronts, public platform-owner flows, payment vault, monitoring, APIs, AI surfaces, and owner administration.

> **Proprietary software.** This repository is public for project tracking and continuity, but it does not grant any public license to copy, reuse, modify, redistribute, host, or commercialize the code. See [`LICENSE`](LICENSE).

---

## العربية

**أزاديكسا** منصة ERP وتجـارة ومحاسبة ومخزون ذكية متعددة المستأجرين.

المنصة تدير:

- الشركات/المستأجرين والفروع والمستخدمين والصلاحيات.
- المبيعات، نقاط البيع، المرتجعات، العملاء، والمدفوعات.
- المشتريات، الموردين، الشيكات، المصاريف، والصناديق.
- المنتجات، التصنيفات، المستودعات، الحركات، السيريالات، تكلفة المخزون، ومتوسط التكلفة.
- دفتر الأستاذ العام، القيود اليومية، شجرة الحسابات، الفترات، التسويات، الموازنات، الأصول، ومراكز التكلفة والربح.
- متجر خاص لكل مستأجر مرتبط بمستودع أونلاين خاص به.
- صفحات عامة للاندنج، التبرعات، وشراء الحزم كجزء من نطاق مالك المنصة.
- خزنة دفع وعمليات حساسة خاصة بمالك المنصة.
- تكاملات وتقارير ومراقبة وواجهات API وGraphQL وAI عند تفعيلها.

القاعدة الأساسية: **كل مستأجر له بياناته وعملياته ومتجره ومحاسبته، بينما صفحات اللاندنج والتبرعات وشراء الحزم وخزنة الدفع العامة هي نطاق مالك المنصة.**

---

## Product Identity

| Item | Value |
|------|-------|
| Product | Azadexa / أزاديكسا |
| Company | AZAD Intelligent Systems |
| System type | Multi-Tenant ERP SaaS / Commerce and Accounting Platform |
| Repository | `AbuAzad2025/Azad-UAE` |
| License | Proprietary / All Rights Reserved |

Recommended positioning:

```text
Azadexa — Intelligent ERP, Accounting & Commerce Platform
```

---

## System Surfaces

The codebase registers a broad set of modules: sales, POS, returns, customers, suppliers, purchases, products, warehouse, unified inventory, branches, payments, checks, expenses, ledger, advanced ledger, admin ledger, payroll, reports, treasury, tenant store, public shop, payment vault, monitoring, analytics API, API docs, GraphQL, gamification, AI, users, tenants, language, WhatsApp, public pages, and owner control.

See [`docs/SYSTEM_MODULES.md`](docs/SYSTEM_MODULES.md) for the code-derived module map.

---

## Core Domains

| Domain | What it covers |
|--------|----------------|
| Tenant ERP | tenant-specific sales, purchases, customers, suppliers, branches, users, roles, permissions |
| Inventory | products, warehouses, stock movements, warehouse stock, serials, warranty, cost history, MWAC/WAC support |
| Accounting | GL accounts, journal entries, journal lines, periods, mappings, budgets, assets, reconciliation, cost/profit centers |
| Payments | tenant payments/receipts, cheques, pending confirmations, rejected cheque reversal behavior |
| Commerce | tenant store settings, public catalog, checkout, coupons, variants, loyalty, reviews, saved accounts, stock alerts |
| Platform owner | owner panel, package purchases, public donation/payment flows, payment vault, platform-level controls |
| Integrations | WhatsApp, APIs, GraphQL, analytics, monitoring, AI fallback/features |

---

## Tenant Model

Azadexa is multi-tenant by design.

- Normal company users are locked to their own `tenant_id`.
- Platform owner users can switch active tenant context.
- Tenant-owned models are protected through ORM scoping and explicit tenant helpers.
- Storefront routes resolve tenant context from the store slug/domain and must explicitly filter by that tenant.
- User management is specially scoped because `User` is exempt from automatic ORM scoping for Flask-Login loading.

See [`docs/SECURITY_AND_TENANCY.md`](docs/SECURITY_AND_TENANCY.md).

---

## Accounting and Inventory Model

Financial and stock operations are first-class system behavior.

- Sales calculate subtotals, discounts, tax, currency/base amount, confirmed payments, pending checks, returns, and balance due.
- Purchases support supplier linkage, warehouse/branch context, landed-cost components, and base-currency amounts.
- GL posting is mandatory for financial documents that require accounting impact.
- Stock movements update per-warehouse stock and legacy product stock while preserving movement history.
- MWAC/WAC cost tracking uses warehouse-level cost and cost history where enabled.
- Returns and reversals must be traceable, not silent deletes.

See [`docs/ACCOUNTING_AND_INVENTORY_RULES.md`](docs/ACCOUNTING_AND_INVENTORY_RULES.md).

---

## Store and Platform Payment Boundaries

Azadexa has two different commerce/payment meanings:

1. **Tenant store commerce** — each tenant can have a tenant-specific public store, tied to its own online warehouse and tenant products.
2. **Platform-owner public flows** — landing pages, donations, package purchases, and platform payment vault belong to AZAD/platform-owner scope.

These must not be mixed. Tenant store orders are tenant operations; public donations and package purchases are platform-owner revenue flows unless an explicit business rule says otherwise.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/README.md`](docs/README.md) | Documentation index |
| [`docs/AZADEXA_BRAND.md`](docs/AZADEXA_BRAND.md) | Product name, positioning, Arabic/English brand rules |
| [`docs/SYSTEM_MODULES.md`](docs/SYSTEM_MODULES.md) | Code-derived module and model map |
| [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) | Business and system overview |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture, tenant model, service boundaries |
| [`docs/SECURITY_AND_TENANCY.md`](docs/SECURITY_AND_TENANCY.md) | Tenant isolation, owner-only flows, public/store/payment boundaries |
| [`docs/ACCOUNTING_AND_INVENTORY_RULES.md`](docs/ACCOUNTING_AND_INVENTORY_RULES.md) | Ledger, payment, stock, returns, MWAC, and balance rules |
| [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) | Internal operating model and incident thinking, not deployment instructions |
| [`AGENTS.md`](AGENTS.md) | Rules for AI coding assistants and internal automation |

---

## Development Guardrails

Before changing code, identify the scope:

```text
tenant-scoped / branch-scoped / tenant-store-scoped / platform-owner-scoped / public
```

Do not casually change:

- tenant filters;
- owner-only guards;
- payment vault boundaries;
- customer/supplier balance logic;
- GL debit/credit posting;
- stock movement and warehouse cost logic;
- tenant store slug/domain resolution;
- public donation/package payment ownership.

Read [`AGENTS.md`](AGENTS.md) before using AI coding assistants on this repository.

---

## Ownership

**Product:** Azadexa / أزاديكسا  
**Company:** AZAD Intelligent Systems  
**Owner:** Eng. Ahmad Ghannam  
**Contact:** rafideen.ahmadghannam@gmail.com — 0562150193 / +972562150193  
**License model:** Proprietary / All Rights Reserved

© 2026 AZAD Intelligent Systems — All Rights Reserved.
