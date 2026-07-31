# Azadexa — Intelligent ERP, Accounting & Commerce Platform

![CI](https://github.com/AbuAzad2025/Azad-UAE/actions/workflows/ci.yml/badge.svg)

**Azadexa** (أزاديكسا) is a multi-tenant ERP, accounting, inventory, and commerce platform built for SMEs worldwide by **AZAD Intelligent Systems**. It is country-agnostic: each tenant configures its own country, currency, VAT regime, and timezone.

---

## Overview

Azadexa is a complete business operating system — not a template, not a demo. It manages the full lifecycle of a company: sales, purchases, inventory, accounting, HR, payroll, e-commerce, and payments — all in one platform with real-time dashboards and multi-currency support.

Each tenant (company) operates in full isolation with its own chart of accounts, warehouses, users, roles, and storefront. The platform owner manages subscriptions, billing, and public-facing flows separately.

---

## Core Capabilities

| Module | What It Does |
|--------|-------------|
| **Sales & POS** | Touch-optimized point of sale, split tender, returns, promotions engine, parked carts, manager overrides, e-invoicing with QR |
| **Purchases** | Supplier management, purchase orders, landed cost, returns, GL posting |
| **Inventory** | Multi-warehouse, barcode/QR scanning, batch & serial tracking, expiry alerts, MWAC/WAC costing, stock transfers |
| **Double-Entry Accounting** | Full GL with dynamic account mapping, journal entries, trial balance, balance sheet, income statement, cost centers, budgets, fixed asset depreciation |
| **Payments & Treasury** | Payment receipts, cheque lifecycle, bank reconciliation, cash flow analysis, FX revaluation |
| **HR & Payroll** | Employee profiles, attendance, leave management, payroll processing, loans & overtime |
| **E-Commerce** | Tenant-specific storefront with unified multi-currency display pricing, cart, checkout, coupons, loyalty, reviews, wishlist, stock alerts, and per-order platform commission tracking |
| **CRM** | Lead pipeline, campaign management, email marketing |
| **Projects** | Project tracking, timesheets, resource allocation |
| **Integrations** | REST API, GraphQL, WhatsApp, webhooks, OpenAPI documentation |
| **Analytics** | Real-time dashboards, custom reports, data export (Excel/PDF) |
| **Multi-Currency** | Live exchange rates with graceful stored-rate fallback, currency conversion, FX revaluation, tenant base currency |
| **Bilingual** | Full Arabic/English support with RTL layout |

---

## Platform Architecture

```
┌─────────────────────────────────────────────────┐
│                AZADEXA PLATFORM                  │
├──────────────┬──────────────┬───────────────────┤
│   Tenant A   │   Tenant B   │   Platform Owner   │
│  ─────────   │  ─────────   │   ──────────────   │
│  Sales       │  Sales       │   Subscriptions    │
│  Inventory   │  Inventory   │   Billing          │
│  Accounting  │  Accounting  │   Payment Vault    │
│  POS         │  POS         │   Public Pages     │
│  Store       │  Store       │   Donations        │
│  HR/Payroll  │  HR/Payroll  │   Analytics        │
└──────────────┴──────────────┴───────────────────┘
```

- **Multi-tenant isolation** at the ORM level — no cross-tenant data leakage
- **Branch-aware workflows** — each tenant can operate multiple branches
- **Role-based access control** — granular permissions per module
- **Automated backups** with scoped restore

---

## Who It's For

| Industry | Use Case |
|----------|----------|
| Auto Parts | Multi-warehouse stock, serial tracking, supplier management |
| Retail & Supermarket | POS, barcode scanning, inventory, e-invoicing |
| Restaurants | Touch POS, kitchen display, order management |
| Enterprise | Multi-branch, HR/payroll, advanced accounting |
| Workshops | Project tracking, parts inventory, invoicing |

---

## Pricing

| Plan | Price | Users | Includes |
|------|-------|-------|----------|
| **Starter** | $29/mo | Up to 3 | Sales, purchases, inventory, e-invoices, basic reports |
| **Professional** | $79/mo | Up to 10 | All Starter + GL, POS, online store, AI features, advanced reports |
| **Enterprise** | $249/mo | Unlimited | All features + HR/payroll, AI insights, daily backups, 24/7 support |

Add-on modules: POS (+$10), Online Store (+$10), HR & Payroll (+$10), AI Assistant (+$15), Multi-Branch (+$10), Restaurant (+$12).

All plans include: GL, inventory, invoices, multi-currency, cheque management, reports, and fixed assets.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.14, Flask 3.1, SQLAlchemy 2.0 |
| Database | PostgreSQL (with connection pooling) |
| Caching | Redis |
| Task Queue | Celery |
| Real-time | WebSocket (SocketIO) |
| API | REST + GraphQL + OpenAPI |
| PDF/Print | WeasyPrint |
| Payments | NOWPayments (crypto), Stripe, encrypted card vault |
| Testing | 10,000+ unit tests, integration & E2E suites |
| Security | CSRF, rate limiting, CSP headers, tenant ORM isolation |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | System design, tenant model, security compliance |
| [`docs/user-guide.md`](docs/user-guide.md) | Module workflows for tenant users |
| [`docs/api.md`](docs/api.md) | REST & GraphQL integration specifications |
| [`SECURITY.md`](SECURITY.md) | Security policies and vulnerability disclosure |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development standards and contribution guidelines |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Product roadmap and upcoming features |

---

## License

**Proprietary software** — All Rights Reserved.

This repository is public for project tracking and continuity. It does not grant any public license to copy, reuse, modify, redistribute, host, or commercialize the code. See [`LICENSE`](LICENSE).

---

## Funding & Sponsorship

AZAD Intelligent Systems accepts direct sponsorship and investment through the following verified channels:

| Channel | Details |
|---------|---------|
| **GitHub Sponsors** | [Sponsor AbuAzad2025](https://github.com/sponsors/AbuAzad2025) |
| **WhatsApp** | [Message Us](https://wa.me/972562150193) |
| **Email** | [rafideen.ahmadghannam@gmail.com](mailto:rafideen.ahmadghannam@gmail.com?subject=GitHub%20Repository%20Sponsorship%20%26%20IBAN) |

### Direct Bank Transfer (IBAN)

For enterprise sponsors and institutional investors preferring direct wire transfers:

- **IBAN:** `PS54 TNBC 0204 0037 4080 0320 0000 0`
- **Account Name:** AZAD Intelligent Systems
- **Contact for Confirmation:** [rafideen.ahmadghannam@gmail.com](mailto:rafideen.ahmadghannam@gmail.com) | WhatsApp: `+972 56 215 0193`

---

## Contact

**AZAD Intelligent Systems** | شركة أزاد للأنظمة الذكية

| Channel | Contact Info |
|---|---|
| Direct Email | rafideen.ahmadghannam@gmail.com |
| Phone / WhatsApp | +972 56 215 0193 |
| WhatsApp Direct | [Message Us](https://wa.me/972562150193) |

© 2026 AZAD Intelligent Systems — All Rights Reserved.
