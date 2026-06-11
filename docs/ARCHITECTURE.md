# Azadexa Architecture

This document describes the code-derived architecture of **Azadexa**, the intelligent multi-tenant ERP, accounting, inventory, and commerce platform by **AZAD Intelligent Systems**.

Azadexa is not a single module application. It is a layered Flask system with tenant ERP, branch operations, GL accounting, warehouse inventory, tenant storefronts, platform-owner payment flows, public pages, APIs, monitoring, and optional AI surfaces.

---

## Architecture goals

Azadexa must support:

- tenant isolation as a core architecture rule;
- branch-aware visibility and warehouse access;
- reliable ERP workflows for sales, purchases, returns, payments, and cheques;
- correct accounting and GL posting behavior;
- traceable inventory movement and warehouse-level costing;
- tenant-owned storefronts and public catalog/checkout behavior;
- separate platform-owner flows for packages, donations, payment vault, and owner controls;
- Arabic-first professional ERP UI;
- maintainable service boundaries;
- safe API, GraphQL, monitoring, WhatsApp, gamification, and AI surfaces.

---

## System request style

Azadexa follows a layered request structure:

```text
HTTP request
  -> Flask blueprint route
  -> login / permission / owner / company-admin decorator
  -> tenant, branch, store, or platform-owner scope resolution
  -> service layer for business logic
  -> SQLAlchemy models
  -> database mutation or query
  -> template, redirect, or JSON response
```

Complex business logic should live in services, not in templates or route handlers.

---

## Blueprint surface

`bootstrap/blueprints.py` registers a broad system surface:

| Surface | Main responsibility |
|---------|---------------------|
| `auth`, `users`, `tenants`, `language` | identity, user management, tenant context, language |
| `main`, `public`, `owner` | dashboard, public pages, platform-owner panel |
| `sales`, `pos`, `returns`, `payments`, `cheques` | selling, payment, return, receipt, cheque lifecycle |
| `customers`, `suppliers`, `partners` | business parties, statements, partner behavior |
| `purchases`, `expenses`, `treasury`, `payroll` | purchase-side, expenses, treasury, payroll |
| `products`, `warehouse`, `unified_inventory` | product catalog, stock movement, warehouse inventory |
| `ledger`, `advanced_ledger`, `admin_ledger`, `reports` | GL, accounting, financial reports, admin ledger surfaces |
| `store`, `shop` | tenant store administration and public tenant storefront |
| `payment_vault` | platform-owner payment vault and provider settings |
| `monitoring`, `api`, `api_enhanced`, `api_analytics`, `api_docs`, `graphql` | control/API/observability surfaces |
| `whatsapp`, `gamification`, `ai` | integrations, engagement, AI assistant/features |

The architecture should preserve these surfaces instead of collapsing them into a generic “shop” or “accounting app”.

---

## Model families

The model registry shows these main families:

| Family | Important models |
|--------|------------------|
| Access | `User`, `Role`, `Permission`, `LoginHistory`, `SecurityAlert`, `APIKey` |
| Tenant structure | `Tenant`, `Branch`, `InvoiceSettings`, `SystemSettings`, `IntegrationSettings` |
| Sales/purchases | `Sale`, `SaleLine`, `Purchase`, `PurchaseLine`, `ProductReturn`, `ProductReturnLine` |
| Payments | `Payment`, `Receipt`, `Cheque`, `CashBox` |
| Inventory | `Product`, `ProductCategory`, `ProductSerial`, `Warehouse`, `StockMovement`, `ProductWarehouseStock` |
| Costing | `ProductWarehouseCost`, `ProductCostHistory` |
| GL/accounting | `GLAccount`, `GLJournalEntry`, `GLJournalLine`, `GLPeriod`, `GLAccountMapping`, `JournalEntryAudit` |
| Advanced finance | `BankReconciliation`, `Budget`, `CostCenter`, `ProfitCenter`, `FixedAsset`, `DepreciationSchedule`, `CustomsTax`, `TaxCalculationRule` |
| Tenant commerce | `TenantStore`, `StorePaymentMethod`, `StoreCoupon`, `ShopCustomerAccount`, `ShopWishlist`, `ShopReview`, `ShopLoyalty`, `ShopProductVariant`, `ShopStockAlert`, `Shipment` |
| Platform owner | `PaymentVault`, `PaymentTransaction`, `PaymentLog`, `CardVault`, `CardPayment`, `Donation`, `Package`, `PackagePurchase`, `AzadPlatformFee` |
| Partner/payroll | `Partner`, `PartnerCommissionEntry`, `PartnerProfitDistribution`, `PartnerTransaction`, `Employee`, `SalaryAdvance`, `PayrollTransaction` |

---

## Main layers

| Layer | Purpose |
|------|---------|
| `routes/` | HTTP endpoints, page rendering, request validation, permission gates |
| `services/` | business rules, accounting posting, stock movement, store checkout, reporting, monitoring |
| `models/` | SQLAlchemy tables, relationships, domain methods |
| `utils/` | tenant helpers, decorators, branching, validators, constants, GL references |
| `templates/` | Arabic-first and RTL-aware ERP UI |
| `static/` | CSS, JavaScript, images, frontend behavior |
| `migrations/` | database schema evolution |
| `runtime_core/` | startup integrity and idempotent repairs |
| `tools/` | development, QA, audit, and maintenance utilities |
| `docs/` | system identity, flows, architecture, tenancy, accounting, inventory, and agent rules |

---

## Request handling principles

Every route should answer these questions before reading or mutating data:

1. Is the user authenticated, anonymous/public, tenant admin, branch user, accountant, or platform owner?
2. What permission or decorator is required?
3. Is this tenant-scoped, branch-scoped, tenant-store-scoped, platform-owner-scoped, or public?
4. How is tenant id resolved?
5. Is branch or warehouse access required?
6. Does the query use tenant scoping, tenant helper, store tenant resolution, or owner-only context?
7. Does the operation affect stock, GL, balances, payments, cheques, returns, or owner vault data?
8. Is the operation traceable by source document and reference type?

---

## Tenant architecture

Azadexa uses layered tenant isolation:

- `utils.tenanting.get_active_tenant_id()` locks normal users to `user.tenant_id`.
- Platform-owner users may switch active tenant context through session.
- `tenant_query`, `tenant_get`, and `tenant_get_or_404` provide explicit query helpers.
- `utils.tenant_orm` injects ORM criteria into SELECT statements for mapped models with `tenant_id`.
- `Session.get()` is patched to reject cross-tenant objects when tenant scope is enabled.
- `User` is exempt from automatic ORM scoping because Flask-Login loads users by id; user management must scope explicitly.
- `shop` is intentionally exempt from automatic ORM scoping because public storefront routes resolve tenant from store slug/domain and must explicitly filter by `store.tenant_id`.

Tenant isolation is not a UI feature; it is a data-access architecture rule.

---

## Scope types

| Scope | Description | Examples |
|------|-------------|----------|
| Tenant ERP scope | Business data belonging to one tenant | sales, purchases, inventory, customers, suppliers, tenant accounting |
| Branch scope | Sub-scope inside a tenant | branch-specific sales, stock, users, reports, liquidity accounts |
| Tenant store scope | Public commerce data for one tenant | catalog, cart, checkout, order token, loyalty, coupons |
| Platform-owner scope | System owner operations | packages, donations, public revenue, owner vault, global store lock |
| Public scope | Anonymous pages with limited safe behavior | landing, pricing/packages, public store catalog |

---

## Sales architecture

Sales are handled as business documents with multiple side effects.

`SaleService.create_sale()` validates customer, seller, line data, currency, discount, tax, warehouse, serials, stock availability, and creates sale header/lines. It can defer fulfillment for online store orders.

`SaleService.fulfill_sale()` performs the operational side:

- validates stock again;
- creates stock movements;
- creates payment record if payment data exists;
- recalculates totals and customer classification;
- ensures GL accounts;
- calculates COGS;
- posts revenue/VAT/discount GL lines;
- posts COGS and inventory asset GL lines;
- posts partner commissions;
- applies customer sale/receipt effects.

This separation is important: a pending online order is not the same as a fulfilled sale.

---

## Purchase architecture

Purchases are supplier-side documents with inventory and accounting effects.

The purchase model supports:

- tenant-aware purchase numbers;
- supplier, branch, and warehouse references;
- subtotal, discount, tax, total, currency, and base amount;
- landed cost components: freight, insurance, customs duty, other landed cost;
- purchase lines with landed unit cost.

Purchase processing should update stock, cost, payable/accounting behavior, and supplier balances consistently.

---

## Inventory and costing architecture

Inventory is movement-based.

`StockService.create_movement()` creates tenant-aware stock movement records, updates `ProductWarehouseStock`, and updates legacy `Product.current_stock`.

Warehouse-level costing uses:

- `ProductWarehouseCost` for quantity, total value, and average cost;
- `ProductCostHistory` for audit history;
- purchase receipt to update WAC/MWAC using landed unit cost;
- sale fulfillment to calculate COGS and reduce stock value;
- sale reversal to restore stock and cost based on original cost history where possible.

Direct quantity manipulation should be avoided in favor of movement-based behavior.

---

## Accounting architecture

GL posting is centralized.

`post_or_fail()` delegates to `GLService.post_entry()` and raises if a journal entry cannot be posted. `GLService` resolves tenant chart of accounts, concept mappings, liquidity accounts, VAT accounts, customer credit accounts, and validates balanced debit/credit totals.

Important GL concepts:

- tenant chart of accounts;
- branch-aware liquidity account resolution;
- account concept mapping through `GLAccountMapping`;
- journal entries and lines with source reference type/id;
- financial dimensions on lines: branch, warehouse, cost center, profit center, partner;
- period locking;
- reversing entries;
- VAT reporting.

---

## Payment architecture

Tenant payments use `Payment` and `Receipt` models with:

- tenant-aware payment/receipt numbers;
- incoming/outgoing direction;
- sale, purchase, customer, supplier, branch references;
- method normalization;
- confirmed vs pending/rejected cheque state;
- recalculation of sale status when cheque/payment state changes.

Platform-owner payment flows are separate and use vault/package/donation/payment-vault models.

---

## Store architecture

A tenant store is not a global marketplace bucket. It is one store per tenant.

`TenantStore` stores tenant id, online warehouse id, enabled state, platform disabled state, slug, domain/subdomain, SEO fields, contact data, low-stock threshold, and notification settings.

`StoreService` manages:

- online warehouse creation;
- one tenant store per tenant;
- slug/subdomain uniqueness;
- public availability checks;
- public catalog from in-stock online warehouse products only;
- tenant-specific cart session keys;
- coupons, variants, loyalty, and related store features.

`StoreCheckoutService` creates tenant sales with `source='online_store'` and `sale_status='pending'` using deferred fulfillment.

---

## Platform-owner architecture

Owner functionality is separate from tenant administration.

Owner/platform features include:

- owner panel;
- platform payment vault;
- card/payment vault surfaces;
- package and package purchase records;
- public donations;
- platform fee concepts;
- tenant administration;
- global controls such as store enablement and platform hard-locking.

Owner-only is not equivalent to tenant `super_admin`.

---

## Frontend architecture

The UI is Arabic-first and RTL-oriented. Frontend changes should preserve:

- RTL layout correctness;
- professional Arabic business wording;
- ERP tone instead of beginner/demo language;
- responsive tables and dashboards;
- form validation;
- accessibility improvements;
- print/export behavior;
- tenant-specific branding where applicable.

---

## Service boundaries

Prefer services for:

- sale creation and fulfillment;
- purchase processing;
- stock movement and costing;
- GL posting and account resolution;
- payment and cheque state transitions;
- store catalog and checkout;
- owner/payment-vault behavior;
- monitoring and reports;
- reusable validation logic.

Routes should stay thin where possible: validate request, enforce permissions, call service, return response.

---

## Change review checklist

Before merging architecture-sensitive changes, verify:

- tenant id is applied correctly;
- branch/warehouse scope is preserved;
- owner-only routes remain owner-only;
- tenant store routes resolve and filter by store tenant;
- accounting side effects are balanced and referenced;
- inventory side effects are movement-based;
- payment ownership is clear;
- public routes expose only public data;
- templates do not expose unauthorized data;
- tests or manual QA cover the changed path.
