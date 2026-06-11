# Azadexa Accounting and Inventory Rules

This document defines the financial and inventory expectations for **Azadexa**, the intelligent multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

The goal is to prevent accidental corruption of balances, stock quantities, tenant accounting, supplier/customer ledgers, and platform-owner payment flows.

---

## Core rule

Every accounting or inventory operation must answer:

```text
Who owns this transaction?
What document caused it?
What accounts or stock records are affected?
Can it be audited, reversed, or corrected safely?
```

---

## Ownership rules

| Operation | Owner scope |
|----------|-------------|
| Tenant sale | Tenant |
| Tenant purchase | Tenant |
| Tenant stock movement | Tenant |
| Tenant customer balance | Tenant |
| Tenant supplier balance | Tenant |
| Tenant store order | Tenant / tenant store |
| Public donation | Platform owner |
| Package purchase | Platform owner |
| Owner vault/card operation | Platform owner only |

Do not mix platform-owner revenue with tenant accounting unless there is a deliberate, documented business rule.

---

## Accounting workflow checklist

Before changing any accounting logic, verify:

- tenant id is known and enforced;
- branch id is applied when needed;
- source document type and id are preserved;
- debit and credit are balanced;
- customer/supplier balances match source documents;
- payment status matches ledger status;
- returns/voids/reversals do not duplicate balances;
- currency handling is consistent;
- reports read from the same source of truth;
- audit trail is preserved.

---

## Ledger rules

A journal entry should include:

- tenant id;
- date;
- source module;
- source document id;
- debit account;
- credit account;
- amount;
- currency where applicable;
- description;
- created by / created at;
- reversal link when applicable.

No accounting entry should be created without a clear source.

---

## Customer balance rules

Customer balance calculations should be traceable from:

- sales invoices;
- payments;
- returns;
- discounts/adjustments;
- opening balances if supported;
- ledger entries if the report depends on GL.

Avoid maintaining multiple independent balance calculations that can diverge.

---

## Supplier balance rules

Supplier balance calculations should be traceable from:

- purchase invoices;
- payments to supplier;
- purchase returns;
- discounts/adjustments;
- opening balances if supported;
- ledger entries if the report depends on GL.

---

## Inventory movement rules

Every stock-changing operation should create or reference a movement trail.

A movement should include:

- tenant id;
- branch id where relevant;
- warehouse id;
- product id;
- quantity before/after or quantity delta;
- movement type;
- source document type and id;
- user/action;
- timestamp;
- reversal or correction reference where applicable.

---

## Sales inventory rules

A sale may affect inventory when products are stock-managed.

Check:

- product belongs to the active tenant;
- stock is pulled from the correct warehouse/branch;
- quantities are not deducted twice;
- cancelled/voided sales restore stock only once;
- returns create the correct reverse movement;
- accounting entries match the business rule.

---

## Purchase inventory rules

A purchase may increase inventory when products are stock-managed.

Check:

- supplier belongs to the active tenant;
- warehouse is tenant-scoped;
- received quantities are recorded correctly;
- purchase returns reduce stock correctly;
- supplier balance and stock movement remain consistent;
- accounting entries match the business rule.

---

## Returns and reversals

Returns and reversals must not be implemented as silent deletes.

Preferred behavior:

- keep the original document;
- create a reversal/return document;
- link the reversal to the original source;
- reverse accounting impact explicitly;
- reverse inventory impact explicitly;
- keep audit trail.

---

## Direct database edits

Direct edits to financial or stock tables are dangerous.

Do not manually edit production records unless:

- there is a documented incident;
- a backup exists;
- the correction script is reviewed;
- the affected tenant and documents are known;
- the correction creates an audit trail or an incident note.

---

## Reports consistency

Financial reports should not invent numbers from unrelated sources.

When building or changing reports, define:

- source tables;
- date range rules;
- tenant/branch filters;
- currency rules;
- inclusion/exclusion of voided records;
- whether values are document-based or ledger-based.

---

## Testing expectations

For any change in accounting or inventory logic, test at least:

- one tenant with one branch;
- two tenants to confirm isolation;
- sale create/payment/cancel or return;
- purchase create/payment/return;
- stock movement after sale and purchase;
- customer/supplier statement;
- GL report or ledger impact where applicable.

---

## Red flags

Stop and review if a change includes:

- removing `tenant_id` filters;
- global queries in financial modules;
- direct quantity updates without movement records;
- customer/supplier balance recalculation without source documents;
- owner revenue mixed into tenant accounts;
- deleting invoices or payments instead of reversing;
- changing debit/credit logic without an accounting explanation;
- bypassing service-layer posting logic.
