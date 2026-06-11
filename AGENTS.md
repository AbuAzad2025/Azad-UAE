# AI and Developer Agent Instructions for Azadexa

This repository contains **Azadexa**, a proprietary multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

These instructions apply to AI coding assistants, internal developers, and automation agents working on this repository.

---

## Product identity

Use the current product identity consistently:

```text
Product: Azadexa / أزاديكسا
Company: AZAD Intelligent Systems
Type: Multi-Tenant ERP SaaS / Commerce Platform
```

Do not describe the project as an Amazon clone, generic shop, demo Flask app, or open-source starter.

---

## First rule

Before modifying code, understand the scope:

```text
Is this tenant-scoped, branch-scoped, store-scoped, platform-owner scoped, or public?
```

Most dangerous bugs in this project come from mixing these scopes.

---

## Mandatory reading before major changes

Read these files first:

1. `README.md`
2. `docs/PROJECT_OVERVIEW.md`
3. `docs/ARCHITECTURE.md`
4. `docs/SECURITY_AND_TENANCY.md`
5. `docs/ACCOUNTING_AND_INVENTORY_RULES.md`
6. `docs/OPERATIONS_RUNBOOK.md`
7. `docs/AZADEXA_BRAND.md`

For accounting-heavy work, also inspect any existing accounting blueprints, GL services, ledger routes, and tests before changing calculations.

---

## Hard safety rules

Never do the following without explicit owner approval:

- remove `tenant_id` filters;
- replace tenant-scoped helpers with global queries;
- weaken owner-only decorators or permission checks;
- expose payment vault/card data to tenant users;
- mix platform-owner payments with tenant revenue;
- change accounting debit/credit logic without explaining the financial impact;
- update stock quantities without movement/audit logic;
- run destructive migrations or scripts;
- commit `.env`, backups, database dumps, API keys, card data, or secrets;
- push large rewrites when a surgical patch is enough.

---

## Preferred change style

Use surgical changes.

- Modify the smallest set of files required.
- Preserve existing route names, templates, service calls, and public behavior unless the task asks otherwise.
- Prefer service-layer changes for business logic.
- Keep route handlers focused on permission, validation, service call, and response.
- Preserve Arabic RTL behavior and professional ERP wording.
- Avoid beginner helper text in production UI.
- Do not mass-format unrelated files.

---

## Tenant review checklist

For every route, query, or service touching business data:

- Is the user authenticated where required?
- Is the tenant id enforced?
- Is branch scope enforced where applicable?
- Are tenant store records tenant-scoped?
- Could another tenant see or modify this record?
- Is the operation platform-owner only?
- Are public routes limited to safe public data?

---

## Accounting review checklist

For every accounting or payment change:

- Which tenant or platform owner owns the transaction?
- What source document caused the entry?
- Are debit and credit balanced?
- Are customer/supplier balances consistent?
- Are returns/voids handled as reversals rather than silent deletes?
- Does the report use the correct source of truth?
- Is sensitive payment data masked?

---

## Inventory review checklist

For every stock-changing change:

- Which tenant owns the product?
- Which warehouse/branch is affected?
- Is there a movement record or audit trail?
- Are returns/reversals handled once only?
- Is stock deducted/increased exactly once?
- Does accounting need a corresponding entry?

---

## Testing expectations

Run the narrowest relevant checks first, then broader checks if the change is risky.

Common checks:

```bash
python -m py_compile app.py
pytest tests/unit -v --tb=short
python -m flask db current
```

For route/template changes, also check template compilation tools if present.

For tenant/store/security changes, run or update the relevant QA/security tests before declaring success.

---

## Git and documentation rules

- Keep commits focused and descriptive.
- Update documentation when behavior changes.
- Do not claim tests passed unless they were actually run.
- Do not claim production readiness from docs alone; verify code and runtime behavior.
- If unable to run a check, state that honestly.

---

## Owner policy summary

Tenant stores are tenant-specific.

Public landing pages, donation flows, and package purchase flows are platform-owner flows. Their revenue belongs to the platform owner unless there is an explicit business rule to route it elsewhere.

Owner vault and card/payment management must remain owner-only.
