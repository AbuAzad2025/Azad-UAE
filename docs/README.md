# Azadexa Documentation Index

This directory contains system documentation for **Azadexa**: product identity, module map, system flows, architecture, tenancy, accounting, inventory, platform-owner boundaries, and AI/developer rules.

**Azadexa** is an intelligent multi-tenant ERP, accounting, inventory, and commerce platform by **AZAD Intelligent Systems**.

---

## Core system documents

| Document | Purpose |
|----------|---------|
| [`AZADEXA_BRAND.md`](AZADEXA_BRAND.md) | Product identity, brand wording, Arabic/English naming, positioning rules |
| [`SYSTEM_MODULES.md`](SYSTEM_MODULES.md) | Code-derived module map: blueprints, model families, and platform surfaces |
| [`SYSTEM_FLOWS.md`](SYSTEM_FLOWS.md) | Code-derived business flows: sale, purchase, stock, GL, store, payment, owner flows |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Business scope, actors, domains, tenant/store/platform boundaries |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Technical structure, data flow, tenancy model, service boundaries |
| [`SECURITY_AND_TENANCY.md`](SECURITY_AND_TENANCY.md) | Tenant isolation, owner-only controls, payment boundaries, public/store rules |
| [`ACCOUNTING_AND_INVENTORY_RULES.md`](ACCOUNTING_AND_INVENTORY_RULES.md) | Ledger, balances, stock movement, MWAC/WAC, returns, and financial correctness rules |
| [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md) | System operating model: how tenant, branch, store, GL, stock, and owner scopes behave |
| [`../AGENTS.md`](../AGENTS.md) | Mandatory instructions for AI coding assistants and internal automation |

---

## Existing specialized documents

The repository may also contain additional specialized documentation, such as UI audits, design system notes, QA reports, security audits, accounting blueprints, and feature reports. Those documents should remain source-specific and should be linked from this index when they become stable.

---

## Documentation rules

- Keep product identity consistent: **Azadexa** / **أزاديكسا**.
- Use **AZAD Intelligent Systems** as the company identity.
- Treat this as a proprietary production-bound system, not an open-source starter app.
- Do not turn system documentation into generic deployment notes unless explicitly requested.
- Never document real secrets, production passwords, private keys, card data, or customer data.
- Any public payment, package purchase, or donation flow belongs to the platform-owner scope unless explicitly routed through tenant business logic.
- Tenant storefronts and tenant operations must remain tenant-scoped.
- Accounting and inventory documentation must preserve tenant ownership and auditability.
- Code-derived documents should reflect actual modules, models, services, and route surfaces.

---

## Recommended reading order

1. [`../README.md`](../README.md)
2. [`AZADEXA_BRAND.md`](AZADEXA_BRAND.md)
3. [`SYSTEM_MODULES.md`](SYSTEM_MODULES.md)
4. [`SYSTEM_FLOWS.md`](SYSTEM_FLOWS.md)
5. [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md)
6. [`ARCHITECTURE.md`](ARCHITECTURE.md)
7. [`SECURITY_AND_TENANCY.md`](SECURITY_AND_TENANCY.md)
8. [`ACCOUNTING_AND_INVENTORY_RULES.md`](ACCOUNTING_AND_INVENTORY_RULES.md)
9. [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md)
10. [`../AGENTS.md`](../AGENTS.md)
