# Azadexa Documentation Index

This directory contains the product, architecture, security, operations, deployment, accounting, and brand documentation for **Azadexa**.

**Azadexa** is an intelligent multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

---

## Core documents

| Document | Purpose |
|----------|---------|
| [`AZADEXA_BRAND.md`](AZADEXA_BRAND.md) | Product identity, brand wording, Arabic/English naming, positioning rules |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Business scope, system goals, users, modules, and platform boundaries |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Technical structure, module map, data flow, tenancy model, service boundaries |
| [`SECURITY_AND_TENANCY.md`](SECURITY_AND_TENANCY.md) | Tenant isolation, owner-only controls, payment boundaries, production security rules |
| [`ACCOUNTING_AND_INVENTORY_RULES.md`](ACCOUNTING_AND_INVENTORY_RULES.md) | Ledger, balances, stock movement, returns, and financial correctness rules |
| [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md) | Local/staging/production operations, backup, deployment, incident checklist |
| [`../AGENTS.md`](../AGENTS.md) | Mandatory instructions for AI coding assistants and internal automation |

---

## Existing specialized documents

The repository may also contain additional specialized documentation, such as UI audits, design system notes, deployment guides, QA reports, or accounting blueprints. Those documents should remain source-specific and should be linked from this index when they become stable.

---

## Documentation rules

- Keep product identity consistent: **Azadexa** / **أزاديكسا**.
- Use **AZAD Intelligent Systems** as the company identity.
- Treat this as a proprietary production project, not an open-source starter app.
- Never document real secrets, production passwords, private keys, card data, or customer data.
- Any public payment, package purchase, or donation flow belongs to the platform-owner scope unless explicitly routed through tenant business logic.
- Tenant storefronts and tenant operations must remain tenant-scoped.
- Accounting and inventory documentation must preserve tenant ownership and auditability.

---

## Recommended reading order

1. [`../README.md`](../README.md)
2. [`AZADEXA_BRAND.md`](AZADEXA_BRAND.md)
3. [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md)
4. [`ARCHITECTURE.md`](ARCHITECTURE.md)
5. [`SECURITY_AND_TENANCY.md`](SECURITY_AND_TENANCY.md)
6. [`ACCOUNTING_AND_INVENTORY_RULES.md`](ACCOUNTING_AND_INVENTORY_RULES.md)
7. [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md)
8. [`../AGENTS.md`](../AGENTS.md)
