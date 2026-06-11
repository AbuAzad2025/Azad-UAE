# Azadexa System Flows

This document summarizes the main business flows reflected by the current codebase.

Azadexa is a multi-tenant ERP, accounting, inventory, and commerce platform. Its flows should be understood as connected business events, not isolated UI screens.

---

## 1. Tenant request flow

```text
request
  -> blueprint route
  -> authentication / permission decorator
  -> tenant and branch resolution
  -> model/service query
  -> document, stock, GL, payment, or store action
  -> template / JSON response
```

Tenant scope is resolved through `utils.tenanting` and reinforced by `utils.tenant_orm` for mapped models with `tenant_id`.

---

## 2. Sale creation flow

A normal sale created through `SaleService.create_sale()` performs these steps:

1. Validate customer, seller, line data, currency, discount, tax, and warehouse.
2. Resolve tenant and branch from seller/customer/warehouse context.
3. Generate a tenant-aware sale number.
4. Create `Sale` header.
5. Validate each product line, stock availability, price, discount, and serial numbers if required.
6. Create `SaleLine` records.
7. Calculate subtotal, tax, total, base currency amount, paid amount, balance, and payment status.
8. If fulfillment is not deferred, call `fulfill_sale()`.

---

## 3. Sale fulfillment flow

`SaleService.fulfill_sale()` turns a sale into an operational/accounting event:

1. Confirm customer and warehouse.
2. Prevent duplicate inventory posting.
3. Validate stock availability again.
4. Create stock movements for sold lines.
5. Create payment records when payment data exists.
6. Recalculate sale totals and customer classification.
7. Ensure tenant chart of accounts exists.
8. Calculate COGS through stock costing logic.
9. Post GL revenue/VAT/discount lines.
10. Post COGS and inventory asset GL lines where applicable.
11. Post partner commissions where applicable.
12. Apply customer sale and receipt effects.

Deferred online store orders intentionally stop before fulfillment until confirmed.

---

## 4. Payment and cheque flow

`Payment` and `Receipt` distinguish confirmed payments from pending/rejected cheque states.

Important behavior:

- Cash/card/bank-style payments are normally confirmed immediately.
- Cheques may be pending until cleared.
- Pending cheques should not reduce confirmed receivable/payable balances.
- Confirming a cheque updates the linked sale/payment state.
- Rejecting a cheque marks related payment records as unconfirmed and recalculates affected sale status.

---

## 5. Purchase flow

A purchase is a tenant financial and inventory document.

The purchase model supports:

- tenant-aware purchase numbers;
- supplier and warehouse references;
- branch id;
- subtotal, discount, tax, total;
- currency and base amount;
- landed-cost components: freight, insurance, customs duty, other landed cost;
- purchase lines with landed unit cost.

Purchase stock processing increases warehouse stock and updates product cost. When MWAC/WAC is enabled, warehouse-level cost records are updated.

---

## 6. Inventory movement flow

Stock changes are represented through `StockMovement` and warehouse stock records.

`StockService.create_movement()`:

1. Validates movement type and product.
2. Resolves user and tenant from product/context.
3. Resolves warehouse or creates a main warehouse when needed.
4. Creates movement with tenant, product, warehouse, quantity, reference type, and reference id.
5. Updates `ProductWarehouseStock`.
6. Updates legacy `Product.current_stock`.
7. Rejects negative stock outcomes.

Transfers are represented by paired movement records: one out of the source warehouse and one into the destination warehouse.

---

## 7. Costing flow

When costing is enabled, Azadexa uses warehouse-level cost records:

- `ProductWarehouseCost` stores current quantity, total value, and average cost.
- `ProductCostHistory` stores cost movement history.
- Purchase receipt updates WAC using received quantity and landed unit cost.
- Sale fulfillment calculates COGS and deducts value from warehouse cost records.
- Sale reversal restores quantity/value using original sale cost history where available.

---

## 8. GL posting flow

GL posting is centralized through `services.gl_posting.post_or_fail()` and `services.gl_service.GLService`.

A posting flow should:

1. Receive structured debit/credit lines.
2. Resolve tenant and branch.
3. Resolve GL account by concept mapping or legacy account code.
4. Create `GLJournalEntry`.
5. Create `GLJournalLine` records.
6. Validate debit and credit balance.
7. Preserve reference type and reference id.

Journal lines may carry branch, warehouse, cost center, profit center, and partner dimensions.

---

## 9. Tenant store setup flow

Each tenant can have one online store through `TenantStore`.

`StoreService` manages:

- online warehouse creation;
- one store per tenant;
- slug/subdomain/custom-domain identity;
- enabled state and platform hard-lock state;
- public availability checks;
- catalog products from the tenant online warehouse only;
- cart session key per tenant.

The store is not a global marketplace bucket. It is tenant-owned commerce.

---

## 10. Public tenant store checkout flow

`StoreCheckoutService.create_web_order()`:

1. Resolves tenant from the store.
2. Validates that the store has an online warehouse.
3. Validates payment method for checkout.
4. Builds lines from cart against online warehouse stock.
5. Gets or creates tenant customer.
6. Resolves a tenant seller/system user.
7. Applies coupon if provided.
8. Creates a `Sale` with source `online_store` and status `pending`.
9. Uses deferred fulfillment so stock/GL behavior can be controlled by order confirmation flow.
10. Sends order notification.

---

## 11. Platform-owner payment flow

Platform-owner payment flows are separate from tenant business payments.

They include:

- platform payment vault;
- public donation settings;
- package purchase records;
- payment provider configuration;
- payment logs and platform transaction records.

These flows belong to the platform-owner scope unless explicitly connected to a tenant process by design.

---

## 12. AI/API/monitoring flow

The system also exposes AI, REST APIs, enhanced APIs, analytics APIs, GraphQL, monitoring, WhatsApp, and gamification surfaces.

These surfaces must be treated as entry points into the same tenant, branch, accounting, store, and owner boundaries. They are not bypass channels.
