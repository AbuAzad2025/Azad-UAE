# Azadexa Security Policy

**Azadexa** is a proprietary multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

Security reports must be handled privately because this project includes tenant isolation, accounting, inventory, payment, and platform-owner workflows.

---

## Reporting a vulnerability

If you discover a security vulnerability, do **not** open a public issue with technical exploit details.

Report it privately to the repository owner or the approved internal security contact.

When reporting, include:

- affected route/API/module;
- expected behavior;
- observed behavior;
- reproduction steps;
- affected tenant/platform scope if known;
- screenshots or logs with secrets masked;
- whether payment, card, accounting, inventory, or tenant data is involved.

Do not include real secrets, card data, CVV, private keys, access tokens, or production database exports in the report.

---

## Supported version

| Version / branch | Status |
|------------------|--------|
| `main` | Active internal development and deployment baseline |

---

## High-risk issue categories

Treat the following as high severity until reviewed:

- cross-tenant data visibility or mutation;
- tenant store data leaking to another tenant;
- tenant user access to platform-owner routes;
- public route exposing private tenant data;
- payment webhook manipulation;
- card/payment vault exposure;
- decrypted sensitive data exposed in UI, logs, exports, or APIs;
- SQL injection or unsafe raw SQL;
- authentication bypass;
- authorization bypass;
- accounting balance corruption;
- inventory quantity corruption;
- unsafe backup, restore, or export behavior.

---

## Security design references

Read these documents before changing security-sensitive code:

- [`docs/SECURITY_AND_TENANCY.md`](docs/SECURITY_AND_TENANCY.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/ACCOUNTING_AND_INVENTORY_RULES.md`](docs/ACCOUNTING_AND_INVENTORY_RULES.md)
- [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md)
- [`AGENTS.md`](AGENTS.md)

---

## Production security rules

- Never commit real `.env` files or secrets.
- Never enable debug mode in production.
- Never enable development bypass flags in production.
- Keep payment/card/vault operations owner-only.
- Keep tenant data tenant-scoped.
- Keep public donation/package purchase flows platform-owner scoped.
- Mask sensitive values in logs and exports.
- Test security-sensitive changes on staging before production.

---

## Disclosure policy

This is proprietary software. Vulnerability information, exploit details, private code, customer data, payment details, or deployment secrets must not be disclosed publicly without explicit written approval from the owner.

---

© 2026 AZAD Intelligent Systems — All Rights Reserved.
