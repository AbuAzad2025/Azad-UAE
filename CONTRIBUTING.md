# Contributing to Azadexa

## Important Notice

**Azadexa** is a proprietary project by **AZAD Intelligent Systems**. All rights reserved. This repository is **not open source**.

- Do not fork without explicit written permission.
- Do not submit external pull requests unless invited.
- Do not redistribute the code or any portion of it.
- Do not reuse business logic, templates, assets, or documentation in another product without written approval.

---

## Product context

Azadexa is an intelligent **multi-tenant ERP and commerce platform**. It is not a simple shop, demo app, or open-source framework.

Before changing code, understand whether the work is:

- tenant-scoped;
- branch-scoped;
- tenant-store-scoped;
- platform-owner-scoped;
- public/landing/payment-scoped.

Wrong scope handling can cause cross-tenant leaks, financial errors, or platform-owner data exposure.

---

## Required reading before internal contributions

1. `README.md`
2. `AGENTS.md`
3. `docs/README.md`
4. `docs/PROJECT_OVERVIEW.md`
5. `docs/ARCHITECTURE.md`
6. `docs/SECURITY_AND_TENANCY.md`
7. `docs/ACCOUNTING_AND_INVENTORY_RULES.md`
8. `docs/OPERATIONS_RUNBOOK.md`
9. Existing accounting/security blueprints and tests relevant to the changed area

---

## Internal workflow

1. Start from the latest `main`.
2. Use a focused branch for non-trivial work.
3. Keep changes surgical and scoped.
4. Do not mass-format unrelated files.
5. Run the narrowest relevant tests first.
6. Update documentation when behavior changes.
7. Commit with a clear message describing the business impact.
8. Do not claim tests passed unless they were actually run.

---

## Code standards

- Python 3.11+ compatibility for production deployment.
- UTF-8 encoding for all files.
- Follow existing Flask blueprint, SQLAlchemy, service-layer, and template patterns.
- Prefer services for business rules and financial logic.
- Keep route handlers focused on validation, permission checks, service calls, and responses.
- Preserve Arabic RTL behavior and professional ERP wording.
- Never hardcode secrets, API keys, credentials, card data, or production URLs.

---

## Tenant and security standards

Every tenant-owned query or mutation must enforce tenant ownership.

Before merging tenant-sensitive work, confirm:

- authentication and authorization are correct;
- `tenant_id` is enforced;
- branch scope is enforced where applicable;
- public routes expose only safe public data;
- owner-only routes reject tenant admins;
- payment vault/card workflows remain owner-only;
- tenant store records do not leak across tenants.

---

## Accounting and inventory standards

For financial or stock-changing changes, document and test:

- source document;
- tenant and branch ownership;
- debit/credit impact;
- customer/supplier balance effect;
- inventory movement effect;
- returns/reversals behavior;
- audit trail.

Do not delete or silently overwrite financial history when a reversal or correction record is required.

---

## Testing

Common local checks:

```bash
python -m py_compile app.py
pytest tests/unit -v --tb=short
```

When relevant, also run security, tenant-isolation, template, UI, accounting, or store QA scripts from `tests/` or `tools/qa/`.

Do not run destructive QA tools against production databases.

---

## Documentation updates

Update documentation when behavior changes:

- product identity → `docs/AZADEXA_BRAND.md`;
- system/module scope → `docs/PROJECT_OVERVIEW.md`;
- route/service/data-flow → `docs/ARCHITECTURE.md`;
- tenant/security/payment → `docs/SECURITY_AND_TENANCY.md`;
- accounting/inventory → `docs/ACCOUNTING_AND_INVENTORY_RULES.md`;
- deployment/backup/incident process → `docs/OPERATIONS_RUNBOOK.md`.

---

## Reporting issues

Use the repository's internal issue tracker for normal issues. For security issues, follow `SECURITY.md` and do not disclose vulnerabilities publicly.

---

© 2026 AZAD Intelligent Systems — All Rights Reserved.
