# Azadexa Accounting and Inventory Rules

This document defines the financial and inventory rules for **Azadexa**, the intelligent multi-tenant ERP, accounting, inventory, and commerce platform by **AZAD Intelligent Systems**.

It reflects the current code structure around sales, purchases, payments, cheques, GL posting, stock movements, warehouse costing, landed cost, and tenant store checkout.

---

## Core rule

Every accounting or inventory operation must answer:

```text
Who owns this transaction?
Which tenant and branch are affected?
What source document caused it?
What stock, balance, payment, cheque, or GL records are affected?
Can the effect be traced, reversed, recalculated, or audited?
```

---

## Ownership rules

| Operation | Owner scope |
|----------|-------------|
| Internal tenant sale | Tenant |
| POS sale | Tenant / branch |
| Online tenant store order | Tenant / tenant store |
| Tenant purchase | Tenant |
| Tenant stock movement | Tenant / warehouse |
| Tenant customer balance | Tenant |
| Tenant supplier balance | Tenant |
| Tenant cheque | Tenant / customer or supplier flow |
| Public donation | Platform owner |
| Package purchase | Platform owner |
| Owner vault/card operation | Platform owner only |

Platform-owner revenue must not be mixed into tenant accounting unless a deliberate business rule is created and documented.

---

## Sale document rules

A sale is a financial and inventory document, not just a printed invoice.

The sale model includes:

- tenant id;
- sale number unique per tenant;
- customer, seller, optional sales rep;
- warehouse and branch;
- subtotal, discount, shipping, tax, total;
- currency, exchange rate, base amount;
- paid amount, confirmed base paid amount, balance due;
- payment status;
- source such as `internal` or `online_store`;
- checkout payment method/gateway/coupon fields;
- sale lines with product, quantity, unit price, discount, cost price, and warranty dates.

### Sale totals

Sale totals should be calculated from lines using Decimal precision.

Expected calculation path:

1. `subtotal = sum(line.line_total)`
2. taxable amount = subtotal - discount + shipping
3. tax amount = taxable amount × tax rate
4. total amount = taxable amount + tax
5. amount in base currency = total × exchange rate
6. confirmed paid amount is calculated from confirmed payments only
7. balance due = total base amount - confirmed paid - approved returns

### Payment status

A sale may be:

- `unpaid`;
- `partial`;
- `pending_cheque`;
- `paid`;
- `cancelled` where applicable.

Pending cheques do not reduce confirmed balance until cleared.

---

## Sale fulfillment rules

Sale creation and sale fulfillment are intentionally separate.

`create_sale()` may create the sale document and lines. `fulfill_sale()` performs operational effects:

- validates stock availability again;
- deducts stock through movement records;
- creates payment record when payment data exists;
- recalculates sale totals and customer classification;
- ensures tenant chart of accounts;
- calculates COGS;
- posts revenue/VAT/discount GL entries;
- posts COGS/inventory GL entries;
- posts partner commissions where applicable;
- applies customer balance effects.

Online store orders are created as pending/deferred fulfillment. Do not treat a pending online order as fully delivered until the confirmation/fulfillment flow runs.

---

## Purchase document rules

A purchase is a supplier, inventory, and accounting document.

The purchase model includes:

- tenant id;
- purchase number unique per tenant;
- supplier, warehouse, and branch;
- supplier snapshot fields;
- subtotal, discount, tax, total;
- currency, exchange rate, base amount;
- landed cost components: freight, insurance, customs duty, other landed cost;
- purchase lines with quantity, unit cost, discount, line total, landed cost, and landed unit cost.

### Purchase totals

Expected calculation path:

1. `subtotal = sum(line.line_total)`
2. taxable amount = subtotal - discount
3. tax amount = taxable amount × tax rate
4. total amount = taxable amount + tax + landed cost components
5. base amount = total × exchange rate

### Landed unit cost

`PurchaseLine.landed_unit_cost` should be treated as:

```text
unit cost + allocated landed cost per unit
```

This feeds inventory valuation when purchase stock is processed.

---

## Payment and receipt rules

Payment documents include:

- tenant id;
- payment/receipt number unique per tenant;
- incoming or outgoing direction;
- sale/customer and purchase/supplier references;
- branch id;
- amount, currency, exchange rate, base amount;
- payment method;
- cheque fields where applicable;
- confirmation state and rejection reason.

### Cheque state

Cheques are not the same as confirmed cash.

- Confirmed payment affects confirmed paid amount.
- Pending cheque is visible but does not reduce confirmed balance.
- Rejected cheque must update linked payment records and recalculate affected sale status.

---

## GL posting rules

GL posting is centralized through `post_or_fail()` and `GLService`.

A valid GL posting should include:

- tenant id;
- branch id where relevant;
- description;
- reference type;
- reference id;
- currency;
- exchange rate;
- balanced debit/credit lines;
- concept code or account code;
- financial dimensions when relevant.

Journal lines can carry:

- branch id;
- warehouse id;
- cost center id;
- profit center id;
- partner id.

No financial document should bypass GL posting when the workflow requires accounting impact.

---

## Chart of accounts and mapping rules

The system supports tenant-specific GL accounts and concept mappings.

Important behavior:

- account codes are unique per tenant;
- header accounts cannot receive direct posting;
- inactive accounts cannot receive direct posting;
- concept mappings may resolve accounts dynamically;
- branch-specific mappings may override tenant defaults;
- liquidity accounts may be branch-specific and must be unambiguous;
- periods may prevent posting into closed months.

---

## Customer balance rules

Customer balance calculations should be traceable from:

- sales invoices;
- confirmed payments/receipts;
- pending cheque visibility;
- rejected cheque recalculation;
- returns;
- discounts/adjustments;
- GL entries where reports depend on GL.

Avoid maintaining independent balance logic that diverges from sale/payment/return state.

---

## Supplier balance rules

Supplier balance calculations should be traceable from:

- purchase invoices;
- confirmed outgoing payments;
- supplier-level payment allocation where used;
- purchase returns;
- discounts/adjustments;
- GL entries where reports depend on GL.

---

## Inventory movement rules

Inventory is movement-based.

Every stock-changing operation should create or reference a movement trail with:

- tenant id;
- product id;
- warehouse id;
- movement type;
- quantity delta;
- reference type;
- reference id;
- user id where available;
- notes or source description.

The system updates both warehouse-level stock and legacy product current stock. New logic should prefer warehouse-level stock for precise business decisions.

---

## Warehouse stock rules

Stock availability should be checked against the correct warehouse.

For normal internal/POS sales, warehouse is chosen through seller/branch/selected warehouse logic.

For tenant store checkout, stock must come from the tenant's online warehouse only.

Transfers should be represented as paired movements: a negative movement from source warehouse and a positive movement into destination warehouse.

---

## Costing rules

When MWAC/WAC is enabled:

- purchase receipt updates `ProductWarehouseCost`;
- `ProductCostHistory` records old/new quantity, value, average cost, and movement unit cost;
- sale fulfillment calculates COGS using warehouse average cost when available;
- sale COGS updates warehouse cost records;
- sale reversal restores cost using original cost history where possible.

When MWAC/WAC is disabled or unavailable, sale line cost price is the fallback.

---

## Sales inventory rules

A fulfilled sale may affect inventory.

Check:

- product belongs to the active tenant;
- sale line belongs to sale tenant;
- stock is pulled from the correct warehouse;
- serial numbers are valid and available when required;
- quantities are not deducted twice;
- sale reversal restores stock once;
- COGS and inventory GL entries match the stock effect.

---

## Purchase inventory rules

A purchase may increase inventory.

Check:

- supplier belongs to the tenant;
- warehouse belongs to the tenant;
- received quantities are recorded as movements;
- landed unit cost is applied correctly;
- product cost and warehouse cost are updated consistently;
- supplier balance and GL effects match the purchase document.

---

## Tenant store accounting and stock rules

A tenant store order is still a tenant sale.

Store checkout should:

- resolve tenant from `TenantStore`;
- use the tenant online warehouse;
- validate cart product tenant and online stock;
- reject serial-number products from public checkout if they require phone/manual handling;
- create or update tenant customer;
- create sale with `source='online_store'`;
- mark sale as pending/deferred until fulfillment;
- avoid platform-owner payment mixing unless explicitly designed.

---

## Returns and reversals

Returns and reversals must not be silent deletes.

Preferred behavior:

- keep the original document;
- create reversal/return records;
- link reversal to original source;
- reverse accounting impact explicitly;
- reverse inventory impact explicitly;
- recalculate balances and payment status;
- preserve audit/cost history.

---

## Reports consistency

Reports should define:

- source tables;
- tenant and branch filters;
- date range rules;
- currency/base currency rules;
- document status rules;
- pending cheque inclusion/exclusion;
- whether values are document-based, payment-based, stock-based, or GL-based.

---

## Red flags

Stop and review if a change includes:

- removing `tenant_id` filters;
- global queries in financial modules;
- direct stock quantity edits without movement records;
- payment status changes without recalculating affected sale/customer/supplier state;
- owner revenue mixed into tenant accounts;
- deleting invoices or payments instead of reversing;
- changing debit/credit logic without accounting explanation;
- bypassing `post_or_fail()` where GL posting is required;
- bypassing warehouse-level cost history when MWAC/WAC is enabled;
- treating pending online store order as fulfilled sale.
